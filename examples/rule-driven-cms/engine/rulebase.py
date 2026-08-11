"""Rule-base loading and decision semantics.

A rule base is the *entire domain definition* of a service: entity name and
fields, roles, a lifecycle state machine, environment assumptions, and an
ordered list of allow/deny rules. The engine that executes it (server.py,
decision below) knows nothing about any particular domain.

Decision semantics (Cedar/XACML-style, stated once, used by both the server
and the analyzer):

  1. every rule whose `when` matches the situation is applicable;
  2. if any applicable rule is a deny  -> DENY  (deny overrides allow);
  3. else if any applicable rule is an allow -> ALLOW;
  4. else -> DENY by `default_deny` (nothing is allowed by silence).

The situation vocabulary is derived from the rule base:

  actor.role           enum over declared roles
  actor.active         bool  (deactivated accounts)
  actor.is_author      bool  (is the actor this resource's author?)
  action               enum: read/edit/delete + declared transitions
  resource.state       enum over declared states plus "none" (not created yet)
  resource.has_<field> bool per declared field (field is non-empty)
  resource.<name>      bool per declared projection (see below)

Projections are how facts the rules need but fields don't directly state
enter the vocabulary. `has_<field>` is the built-in kind; a rule base may
declare more, each computed by the engine at request time and treated as a
free boolean by the analyzer:

  projections:
    - {name: is_past_due, kind: date_passed, field: due_date}

Kinds: `date_passed` — field holds an ISO date strictly earlier than the
engine's current date (the clock is engine state: server --today).
"""

import collections
import pathlib

import yaml

from . import conditions

CRUD_ACTIONS = ("read", "edit", "delete")
NO_STATE = "none"
PROJECTION_KINDS = ("date_passed",)

Transition = collections.namedtuple("Transition", "action source target")
Rule = collections.namedtuple("Rule", "id description effect when")
Assumption = collections.namedtuple("Assumption", "id description holds")
Projection = collections.namedtuple("Projection", "name kind field")

DEFAULT_DENY = Rule(
    "default_deny", "No rule allows this action; the default is deny.", "deny", None)


class RuleBaseError(Exception):
    pass


class RuleBase:
    def __init__(self, doc, name):
        self.name = name
        try:
            self.entity = doc["entity"]
            self.roles = tuple(doc["roles"])
            self.states = tuple(doc["states"])
            self.fields = tuple(doc.get("fields", ()))
            transitions = doc["lifecycle"]["transitions"]
            rules = doc["rules"]
        except (KeyError, TypeError) as e:
            raise RuleBaseError(f"{name}: missing/invalid section: {e}") from e

        self.transitions = tuple(
            Transition(t["action"], t["from"], t["to"]) for t in transitions)
        for t in self.transitions:
            for st in (t.source, t.target):
                if st not in self.states + (NO_STATE,):
                    raise RuleBaseError(f"{name}: transition {t.action}: unknown state {st!r}")
            if t.target == NO_STATE:
                raise RuleBaseError(f"{name}: transition {t.action} may not target {NO_STATE!r}")
        # one action may fire from several source states, but each
        # (action, source) pair is unique, and a creating action (from
        # `none`) may not double as a mid-lifecycle one
        pairs = [(t.action, t.source) for t in self.transitions]
        if len(set(pairs)) != len(pairs):
            raise RuleBaseError(f"{name}: duplicate (action, from) transition pairs")
        for t in self.transitions:
            if t.source == NO_STATE and any(
                    o.action == t.action and o.source != NO_STATE for o in self.transitions):
                raise RuleBaseError(f"{name}: creating action {t.action!r} may not "
                                    f"also fire from other states")
        transition_actions = tuple(dict.fromkeys(t.action for t in self.transitions))
        self.actions = CRUD_ACTIONS + transition_actions
        if set(CRUD_ACTIONS) & set(transition_actions):
            raise RuleBaseError(f"{name}: transitions may not reuse {CRUD_ACTIONS}")

        self.projections = tuple(
            Projection(p["name"], p["kind"], p["field"])
            for p in doc.get("projections", ()))
        for p in self.projections:
            if p.kind not in PROJECTION_KINDS:
                raise RuleBaseError(f"{name}: projection {p.name}: unknown kind {p.kind!r}")
            if p.field not in self.fields:
                raise RuleBaseError(f"{name}: projection {p.name}: unknown field {p.field!r}")

        self.vocabulary = conditions.Vocabulary(
            enums={
                "actor.role": self.roles,
                "action": self.actions,
                "resource.state": self.states + (NO_STATE,),
            },
            bools=("actor.active", "actor.is_author")
            + tuple(f"resource.has_{f}" for f in self.fields)
            + tuple(f"resource.{p.name}" for p in self.projections),
        )

        self.assumptions = tuple(
            Assumption(a["id"], a.get("description", ""),
                       conditions.parse(a["holds"], self.vocabulary))
            for a in doc.get("assumptions", ()))

        seen = set()
        parsed = []
        for r in rules:
            if r["id"] in seen:
                raise RuleBaseError(f"{name}: duplicate rule id {r['id']!r}")
            seen.add(r["id"])
            if r["effect"] not in ("allow", "deny"):
                raise RuleBaseError(f"{name}: rule {r['id']}: effect must be allow or deny")
            try:
                when = conditions.parse(r["when"], self.vocabulary)
            except conditions.ConditionError as e:
                raise RuleBaseError(f"{name}: rule {r['id']}: {e}") from e
            parsed.append(Rule(r["id"], r.get("description", ""), r["effect"], when))
        self.rules = tuple(parsed)

    # -- decision -------------------------------------------------------------

    def decide(self, situation):
        """Returns the deciding Rule; effect 'deny' means the request is refused."""
        applicable = [r for r in self.rules if r.when.evaluate(situation)]
        for r in applicable:
            if r.effect == "deny":
                return r
        for r in applicable:
            if r.effect == "allow":
                return r
        return DEFAULT_DENY

    # -- lifecycle legality (structural, checked before the rules) ------------

    def transition_for(self, action, state=None):
        """The transition for `action` — from `state` when given, else the
        first declared one (useful for is-this-a-transition checks)."""
        for t in self.transitions:
            if t.action == action and (state is None or t.source == state):
                return t
        return None

    def creating_transition(self):
        creators = [t for t in self.transitions if t.source == NO_STATE]
        if len(creators) != 1:
            raise RuleBaseError(f"{self.name}: expected exactly one transition from "
                                f"{NO_STATE!r}, found {len(creators)}")
        return creators[0]

    def lifecycle_legal(self, action, state):
        """Is this action structurally applicable to a resource in `state`?"""
        sources = [t.source for t in self.transitions if t.action == action]
        if sources:
            return state in sources
        return state != NO_STATE  # read/edit/delete need an existing resource

    # -- situations ------------------------------------------------------------

    def situation(self, role, active, is_author, action, state,
                  field_values=None, today=None):
        s = {"actor.role": role, "actor.active": bool(active),
             "actor.is_author": bool(is_author), "action": action,
             "resource.state": state}
        for f in self.fields:
            s[f"resource.has_{f}"] = bool((field_values or {}).get(f))
        for p in self.projections:
            s[f"resource.{p.name}"] = _project(p, (field_values or {}).get(p.field), today)
        return s

    def all_situations(self):
        """The full finite situation space (used for exhaustive backend checks)."""
        import itertools
        bool_vars = list(self.vocabulary.bools)
        for role, action, state in itertools.product(
                self.roles, self.actions, self.states + (NO_STATE,)):
            for combo in itertools.product((False, True), repeat=len(bool_vars)):
                s = {"actor.role": role, "action": action, "resource.state": state}
                s.update(zip(bool_vars, combo))
                yield s


def _project(projection, value, today):
    """Compute a declared projection from a concrete field value. ISO date
    strings compare correctly as strings, so no parsing is needed."""
    if projection.kind == "date_passed":
        return bool(value) and today is not None and str(value) < str(today)
    raise AssertionError(projection.kind)


def load(path):
    path = pathlib.Path(path)
    with open(path) as f:
        doc = yaml.safe_load(f)
    return RuleBase(doc, name=str(path))
