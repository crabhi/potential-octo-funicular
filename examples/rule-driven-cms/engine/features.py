"""Feature runs: load the frozen scenario file and replay it.

Two executors share the step semantics:

  * PureExecutor — drives the decision function directly (used by the
    analyzer, no I/O);
  * the HTTP executor in live_demo.py — replays the same file against the
    running service and must observe the same outcomes, including which
    rule denied (the model<->implementation conformance check).

A step acts on the ROOT entity unless it names another: `entity: comment`
targets the (single) live comment, and a child-creating step implicitly
attaches to the live root item — so a feature reads as one story: open a
case, post to it, close it, watch the thread seal. Child decisions are
made with the live parent's CURRENT state as context, exactly as the
kernel decides them at runtime."""

import collections
import datetime

import yaml

from . import rulebase as rb_mod

Actor = collections.namedtuple("Actor", "name role active attrs", defaults=({},))
ANONYMOUS = Actor("anonymous", "anonymous", True, {})


def actor_attrs(actor):
    """The attribute view of an actor that projections match against."""
    return {"name": actor.name, **actor.attrs}

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
        attrs = {k: v for k, v in spec.items() if k not in ("role", "active")}
        actors[name] = Actor(name, spec["role"], spec.get("active", True), attrs)
    return actors, doc.get("features") or [], (doc.get("clock") or {})


class PureExecutor:
    """Replays one feature against the decision function alone. Tracks one
    live item PER ENTITY: {'author':, 'state':, fields...} keyed by name."""

    def __init__(self, rb, actors, today=None):
        self.rb = rb
        self.actors = actors
        self.today = today
        self.items = {}

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
        ent = rb.entity_of(step.get("entity"))
        item = self.items.get(ent.name)
        action = step["action"]
        t_first = ent.transition_for(action)
        creating = t_first is not None and t_first.source == rb_mod.NO_STATE

        # a child's decisions carry its parent's LIVE state as context
        parent = None
        if ent.parent is not None:
            parent = self.items.get(ent.parent.name)
            if parent is None:
                return StepResult(False, f"no {ent.parent.name} exists to parent "
                                         f"this {ent.name}")

        if creating:
            state, is_author = rb_mod.NO_STATE, True
            fields = {f: (step.get("set") or {}).get(f, "") for f in ent.fields}
        elif item is None:
            return StepResult(False, f"no {ent.name} exists yet")
        else:
            state = item["state"]
            is_author = actor.name == item["author"]
            fields = {f: item[f] for f in ent.fields}

        if not ent.lifecycle_legal(action, state):
            return StepResult(False, f"structurally illegal: {action} in state {state}")

        def decide(fields):
            situation = ent.situation(actor.role, actor.active, is_author,
                                      action, state, fields, today=self.today,
                                      actor_attrs=actor_attrs(actor), parent=parent)
            return rb.decide(situation, entity=ent.name)

        verdict = decide(fields)
        if verdict.effect == "allow" and action == "edit":
            # edits are decided twice, here and in the kernel alike: on the
            # current row AND on the row as it would become — a proposed
            # value may not put the resource somewhere the rules refuse
            after = dict(fields)
            for f, v in (step.get("set") or {}).items():
                if f in ent.fields:
                    after[f] = v
            verdict = decide(after)

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
        t = ent.transition_for(action, state) if not creating else t_first
        if creating:
            self.items[ent.name] = {"author": actor.name, "state": t.target, **fields}
        elif t is not None:
            item["state"] = t.target
        elif action == "edit":
            for f, v in (step.get("set") or {}).items():
                if f in ent.fields:
                    item[f] = v
        elif action == "delete":
            del self.items[ent.name]
            if ent.parent is None:  # the store cascades; so does the replay
                self.items.clear()

        want_state = step.get("state_after")
        if want_state:
            live = self.items.get(ent.name)
            have = live["state"] if live else "deleted"
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
