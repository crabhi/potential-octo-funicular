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
"""

import collections
import pathlib

import yaml

from . import conditions

CRUD_ACTIONS = ("read", "edit", "delete")
NO_STATE = "none"

Transition = collections.namedtuple("Transition", "action source target")
Rule = collections.namedtuple("Rule", "id description effect when")
Assumption = collections.namedtuple("Assumption", "id description holds")

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
        self.actions = CRUD_ACTIONS + tuple(t.action for t in self.transitions)
        if len(set(self.actions)) != len(self.actions):
            raise RuleBaseError(f"{name}: duplicate action names in {self.actions}")

        self.vocabulary = conditions.Vocabulary(
            enums={
                "actor.role": self.roles,
                "action": self.actions,
                "resource.state": self.states + (NO_STATE,),
            },
            bools=("actor.active", "actor.is_author")
            + tuple(f"resource.has_{f}" for f in self.fields),
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

    def transition_for(self, action):
        for t in self.transitions:
            if t.action == action:
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
        t = self.transition_for(action)
        if t is not None:
            return state == t.source
        return state != NO_STATE  # read/edit/delete need an existing resource

    # -- situations ------------------------------------------------------------

    def situation(self, role, active, is_author, action, state, field_values=None):
        s = {"actor.role": role, "actor.active": bool(active),
             "actor.is_author": bool(is_author), "action": action,
             "resource.state": state}
        for f in self.fields:
            s[f"resource.has_{f}"] = bool((field_values or {}).get(f))
        return s

    def all_situations(self):
        """The full finite situation space (used for exhaustive backend checks)."""
        import itertools
        bools = (False, True)
        field_combos = list(itertools.product(bools, repeat=len(self.fields)))
        for role, active, is_author, action, state in itertools.product(
                self.roles, bools, bools, self.actions, self.states + (NO_STATE,)):
            for combo in field_combos:
                s = self.situation(role, active, is_author, action, state)
                for f, v in zip(self.fields, combo):
                    s[f"resource.has_{f}"] = v
                yield s


def load(path):
    path = pathlib.Path(path)
    with open(path) as f:
        doc = yaml.safe_load(f)
    return RuleBase(doc, name=str(path))
