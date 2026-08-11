"""Feature runs: load the frozen scenario file and replay it.

Two executors share the step semantics:

  * PureExecutor — drives the decision function directly (used by the
    analyzer, no I/O);
  * the HTTP executor in live_demo.py — replays the same file against the
    running service and must observe the same outcomes, including which
    rule denied (the model<->implementation conformance check).
"""

import collections
import datetime

import yaml

from . import rulebase as rb_mod

Actor = collections.namedtuple("Actor", "name role active")
ANONYMOUS = Actor("anonymous", "anonymous", True)

StepResult = collections.namedtuple("StepResult", "ok message")


class FeatureError(Exception):
    pass


def add_days(iso_date, days):
    return (datetime.date.fromisoformat(iso_date)
            + datetime.timedelta(days=days)).isoformat()


def load(path):
    with open(path) as f:
        doc = yaml.safe_load(f)
    actors = {"anonymous": ANONYMOUS}
    for name, spec in (doc.get("actors") or {}).items():
        actors[name] = Actor(name, spec["role"], spec.get("active", True))
    return actors, doc.get("features") or [], (doc.get("clock") or {})


class PureExecutor:
    """Replays one feature against the decision function alone."""

    def __init__(self, rb, actors, today=None):
        self.rb = rb
        self.actors = actors
        self.today = today
        self.item = None  # {'author':, 'state':, fields...}

    def run(self, feature):
        for i, step in enumerate(feature["steps"], 1):
            res = self.step(step)
            if not res.ok:
                label = step.get("actor", "clock"), step.get("action", "advance")
                return StepResult(False, f"step {i} ({label[0]} {label[1]}): {res.message}")
        return StepResult(True, f"{len(feature['steps'])} steps")

    def step(self, step):
        rb = self.rb
        if "advance_days" in step:
            if self.today is None:
                return StepResult(False, "advance_days without a file-level clock")
            self.today = add_days(self.today, step["advance_days"])
            return StepResult(True, "")
        actor = self.actors[step["actor"]]
        action = step["action"]
        t_first = rb.transition_for(action)
        creating = t_first is not None and t_first.source == rb_mod.NO_STATE

        if creating:
            state, is_author = rb_mod.NO_STATE, True
            fields = {f: (step.get("set") or {}).get(f, "") for f in rb.fields}
        elif self.item is None:
            return StepResult(False, "no item exists yet")
        else:
            state = self.item["state"]
            is_author = actor.name == self.item["author"]
            fields = {f: self.item[f] for f in rb.fields}

        if not rb.lifecycle_legal(action, state):
            return StepResult(False, f"structurally illegal: {action} in state {state}")

        situation = rb.situation(actor.role, actor.active, is_author, action,
                                 state, fields, today=self.today)
        verdict = rb.decide(situation)

        expect = step["expect"]
        got = "allow" if verdict.effect == "allow" else "deny"
        if got != expect:
            return StepResult(False, f"expected {expect}, got {got} (rule: {verdict.id})")
        if expect == "deny":
            want = step.get("denied_by")
            if want and verdict.id != want:
                return StepResult(False, f"denied by {verdict.id}, expected {want}")
            return StepResult(True, "")

        # apply the allowed step
        t = rb.transition_for(action, state) if not creating else t_first
        if creating:
            self.item = {"author": actor.name, "state": t.target, **fields}
        elif t is not None:
            self.item["state"] = t.target
        elif action == "edit":
            for f, v in (step.get("set") or {}).items():
                if f in rb.fields:
                    self.item[f] = v
        elif action == "delete":
            self.item = None

        want_state = step.get("state_after")
        if want_state:
            have = self.item["state"] if self.item else "deleted"
            if have != want_state:
                return StepResult(False, f"state is {have}, expected {want_state}")
        return StepResult(True, "")


def run_all_pure(rb, features_path):
    """Replay every feature purely; returns list of (feature_id, StepResult).
    Each feature starts from the file-level clock (if any)."""
    actors, features, clock = load(features_path)
    results = []
    for feature in features:
        executor = PureExecutor(rb, actors, today=clock.get("today"))
        results.append((feature["id"], executor.run(feature)))
    return results
