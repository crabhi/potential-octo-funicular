"""Rule-base loading and decision semantics.

A rule base is the *entire domain definition* of a service: one or more
entity types (each with fields and a lifecycle), roles, environment
assumptions, and an ordered list of allow/deny rules. The engine that
executes it (server.py, decision below) knows nothing about any particular
domain.

Decision semantics (Cedar/XACML-style, stated once, used by both the server
and the analyzer). A decision is always about ONE entity's action; only the
rules tagged for that entity apply:

  1. every rule (of this entity) whose `when` matches the situation is
     applicable;
  2. if any applicable rule is a deny  -> DENY  (deny overrides allow);
  3. else if any applicable rule is an allow -> ALLOW;
  4. else -> DENY by `default_deny` (nothing is allowed by silence).

The situation vocabulary is derived per entity from the rule base:

  actor.role           enum over declared roles
  actor.active         bool  (deactivated accounts)
  actor.is_author      bool  (is the actor this resource's author?)
  action               enum: read/edit/delete + the entity's transitions
  resource.state       enum over the entity's states plus "none"
  resource.has_<field> bool per declared field (field is non-empty)
  resource.<name>      bool per declared projection (see below)
  parent.state         enum over the PARENT entity's states (children only)
  parent.is_author     bool: is the actor the parent resource's author?
  parent.<name>        bool: a projection of the PARENT entity, computed
                       against the parent row (children only)

Every boolean doubles the situation space, so the vocabulary is a budget.
A field whose emptiness no rule ever mentions can opt out of its automatic
`has_` boolean:

  fields: [title, {name: assignee, has: false}]

Projections are how facts the rules need but fields don't directly state
enter the vocabulary. `has_<field>` is the built-in kind; an entity may
declare more, each computed by the engine at request time and treated as a
free boolean by the analyzer:

  projections:
    - {name: is_past_due, kind: date_passed, field: due_date}
    - {name: same_team,   kind: actor_matches_field, actor_attr: team, field: team}

Kinds: `date_passed` — field holds an ISO date strictly earlier than the
engine's current date (the clock is engine state: server --today);
`actor_matches_field` — the resource field is non-empty and equal to an
attribute of the requesting actor (`name`, or one of the rule base's
declared `actor_fields`). This is how relations between the actor and the
resource — tenancy, assignment — enter the vocabulary as booleans.

Actor fields (`actor_fields: [team]`) are extra per-user attributes stored
with the account and referenced by actor_matches_field projections.

MULTIPLE ENTITY TYPES. The top level of the file describes the ROOT entity
exactly as before (a single-entity rule base is the degenerate case and
loads unchanged). Child entities — comments on a case, attachments — are
declared under `children:`, each belonging to the root:

  children:
    - entity: comment
      states: [posted, redacted]
      fields: [body, {name: internal, has: true}]
      context: [state, is_author, same_org]
      lifecycle:
        transitions:
          - {action: post,   from: none,   to: posted}
          - {action: redact, from: posted, to: redacted}

`context:` is the child's window onto its parent — the ONLY cross-entity
vocabulary, and it is opt-in per atom because it multiplies the child's
situation space. Entries: `state` (the parent's state as an enum — a child
always has a live parent, so "none" is excluded), `is_author` (is the
actor the PARENT's author?), or the name of a projection declared on the
parent (computed against the parent row: tenancy, SLA clocks). This is how
context-sensitive rules are written — "no comments on a closed case" is
`parent.state == "closed"`, decided with the live parent row that the
kernel (never the client) joins in.

Rules and gate properties carry an `entity:` tag — a name or a list of
names — and default to the root, so growing children never touches
existing rules. A rule tagged for several entities is parsed against each
entity's own vocabulary (it must make sense in all of them).

Deliberate limits (not accidents): children cannot have children, a child
has exactly one parent entity, and rules cannot aggregate over children
("close only if no open comments" is not expressible — the parent's rules
cannot see the child table). See research note 16 for why and for the
falsifiers held against these limits.
"""

import collections
import itertools
import pathlib
import re

import yaml

from . import conditions

CRUD_ACTIONS = ("read", "edit", "delete")
NO_STATE = "none"
PROJECTION_KINDS = ("date_passed", "actor_matches_field")
CONTEXT_BUILTINS = ("state", "is_author")

Transition = collections.namedtuple("Transition", "action source target")
Rule = collections.namedtuple("Rule", "id description effect entity when")
Assumption = collections.namedtuple("Assumption", "id description holds")
Projection = collections.namedtuple("Projection", "name kind field actor_attr",
                                     defaults=(None,))

DEFAULT_DENY = Rule(
    "default_deny", "No rule allows this action; the default is deny.",
    "deny", None, None)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RuleBaseError(Exception):
    pass


class Entity:
    """One entity type: states, fields, lifecycle, projections — and, for a
    child entity, the declared window onto its parent (`context`)."""

    def __init__(self, doc, rb_name, roles, actor_fields, parent=None):
        try:
            self.name = doc["entity"]
            self.states = tuple(doc["states"])
            field_specs = [f if isinstance(f, dict) else {"name": f}
                           for f in doc.get("fields", ())]
            self.fields = tuple(f["name"] for f in field_specs)
            self.has_fields = tuple(f["name"] for f in field_specs
                                    if f.get("has", True))
            transitions = doc["lifecycle"]["transitions"]
        except (KeyError, TypeError) as e:
            raise RuleBaseError(f"{rb_name}: missing/invalid section: {e}") from e
        where = f"{rb_name}: entity {self.name}"
        for ident in (self.name,) + self.fields:
            if not _NAME_RE.match(str(ident)):
                raise RuleBaseError(f"{where}: invalid identifier {ident!r}")
        self.parent = parent
        if parent is None and "context" in doc:
            raise RuleBaseError(f"{where}: only child entities have a parent context")
        if parent is not None and "children" in doc:
            raise RuleBaseError(f"{where}: children cannot have children "
                                f"(one level of nesting, by design)")

        self.transitions = tuple(
            Transition(t["action"], t["from"], t["to"]) for t in transitions)
        for t in self.transitions:
            for st in (t.source, t.target):
                if st not in self.states + (NO_STATE,):
                    raise RuleBaseError(f"{where}: transition {t.action}: unknown state {st!r}")
            if t.target == NO_STATE:
                raise RuleBaseError(f"{where}: transition {t.action} may not target {NO_STATE!r}")
        # one action may fire from several source states, but each
        # (action, source) pair is unique, and a creating action (from
        # `none`) may not double as a mid-lifecycle one
        pairs = [(t.action, t.source) for t in self.transitions]
        if len(set(pairs)) != len(pairs):
            raise RuleBaseError(f"{where}: duplicate (action, from) transition pairs")
        for t in self.transitions:
            if t.source == NO_STATE and any(
                    o.action == t.action and o.source != NO_STATE for o in self.transitions):
                raise RuleBaseError(f"{where}: creating action {t.action!r} may not "
                                    f"also fire from other states")
        transition_actions = tuple(dict.fromkeys(t.action for t in self.transitions))
        self.actions = CRUD_ACTIONS + transition_actions
        if set(CRUD_ACTIONS) & set(transition_actions):
            raise RuleBaseError(f"{where}: transitions may not reuse {CRUD_ACTIONS}")

        self.projections = tuple(
            Projection(p["name"], p["kind"], p["field"], p.get("actor_attr"))
            for p in doc.get("projections", ()))
        for p in self.projections:
            if p.kind not in PROJECTION_KINDS:
                raise RuleBaseError(f"{where}: projection {p.name}: unknown kind {p.kind!r}")
            if p.field not in self.fields:
                raise RuleBaseError(f"{where}: projection {p.name}: unknown field {p.field!r}")
            if p.kind == "actor_matches_field":
                if p.actor_attr != "name" and p.actor_attr not in actor_fields:
                    raise RuleBaseError(
                        f"{where}: projection {p.name}: actor_attr {p.actor_attr!r} "
                        f"is neither 'name' nor a declared actor field")

        # the parent context: opt-in, atom by atom (the space is a budget)
        self.context = tuple(doc.get("context", ()))
        parent_projections = {p.name: p for p in parent.projections} if parent else {}
        for c in self.context:
            if c not in CONTEXT_BUILTINS and c not in parent_projections:
                raise RuleBaseError(
                    f"{where}: context {c!r} is neither {'/'.join(CONTEXT_BUILTINS)} "
                    f"nor a projection of the parent entity {parent.name!r}")
        self._parent_projections = parent_projections

        enums = {
            "actor.role": roles,
            "action": self.actions,
            "resource.state": self.states + (NO_STATE,),
        }
        if "state" in self.context:
            # a stored child always has a live parent, so no NO_STATE here
            enums["parent.state"] = parent.states
        self.vocabulary = conditions.Vocabulary(
            enums=enums,
            bools=("actor.active", "actor.is_author")
            + tuple(f"resource.has_{f}" for f in self.has_fields)
            + tuple(f"resource.{p.name}" for p in self.projections)
            + tuple(f"parent.{c}" for c in self.context if c != "state"),
        )

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
            raise RuleBaseError(f"entity {self.name}: expected exactly one transition "
                                f"from {NO_STATE!r}, found {len(creators)}")
        return creators[0]

    def lifecycle_legal(self, action, state):
        """Is this action structurally applicable to a resource in `state`?"""
        sources = [t.source for t in self.transitions if t.action == action]
        if sources:
            return state in sources
        return state != NO_STATE  # read/edit/delete need an existing resource

    # -- situations ------------------------------------------------------------

    def situation(self, role, active, is_author, action, state,
                  field_values=None, today=None, actor_attrs=None, parent=None):
        """The complete vocabulary view of one concrete request. For a child
        entity, `parent` is the live parent ROW (any mapping with state,
        author and the parent's fields) — the kernel joins it in; a client
        never computes context itself."""
        s = {"actor.role": role, "actor.active": bool(active),
             "actor.is_author": bool(is_author), "action": action,
             "resource.state": state}
        for f in self.has_fields:
            s[f"resource.has_{f}"] = bool((field_values or {}).get(f))
        for p in self.projections:
            s[f"resource.{p.name}"] = _project(
                p, (field_values or {}).get(p.field), today, actor_attrs or {})
        if self.context and parent is None:
            raise ValueError(f"entity {self.name} needs its parent row for context")
        for c in self.context:
            if c == "state":
                s["parent.state"] = parent["state"]
            elif c == "is_author":
                s["parent.is_author"] = bool(
                    (actor_attrs or {}).get("name")
                    and actor_attrs["name"] == parent["author"])
            else:
                p = self._parent_projections[c]
                s[f"parent.{c}"] = _project(p, parent[p.field], today,
                                            actor_attrs or {})
        return s

    def all_situations(self):
        """The full finite situation space (used for exhaustive backend
        checks) — the product of every enum domain and every boolean."""
        enum_vars = list(self.vocabulary.enums)
        bool_vars = list(self.vocabulary.bools)
        for values in itertools.product(
                *(self.vocabulary.enums[v] for v in enum_vars)):
            for combo in itertools.product((False, True), repeat=len(bool_vars)):
                s = dict(zip(enum_vars, values))
                s.update(zip(bool_vars, combo))
                yield s


class RuleBase:
    def __init__(self, doc, name):
        self.name = name
        try:
            self.roles = tuple(doc["roles"])
            self.actor_fields = tuple(doc.get("actor_fields", ()))
            rules = doc["rules"]
        except (KeyError, TypeError) as e:
            raise RuleBaseError(f"{name}: missing/invalid section: {e}") from e
        if set(self.actor_fields) & {"name", "role", "active"}:
            raise RuleBaseError(f"{name}: actor_fields may not shadow built-ins")

        # -- entities: the top level IS the root; children are declared under it
        self.root = Entity(doc, name, self.roles, self.actor_fields)
        self.entities = {self.root.name: self.root}
        for child_doc in doc.get("children") or ():
            child = Entity(child_doc, name, self.roles, self.actor_fields,
                           parent=self.root)
            if child.name in self.entities:
                raise RuleBaseError(f"{name}: duplicate entity {child.name!r}")
            self.entities[child.name] = child

        # assumptions are facts about the world (mostly the actor); each is
        # required to make sense for the root and is applied automatically to
        # every child whose vocabulary it also parses in
        self.assumptions = tuple(
            Assumption(a["id"], a.get("description", ""),
                       conditions.parse(a["holds"], self.root.vocabulary))
            for a in doc.get("assumptions", ()))
        self._assumption_docs = tuple(
            (a["id"], a.get("description", ""), a["holds"])
            for a in doc.get("assumptions", ()))

        # -- rules: flat, one Rule per (declared rule x tagged entity) --------
        seen_ids, seen_pairs, parsed = set(), set(), []
        for r in rules:
            if r["id"] in seen_ids:
                raise RuleBaseError(f"{name}: duplicate rule id {r['id']!r}")
            seen_ids.add(r["id"])
            if r["effect"] not in ("allow", "deny"):
                raise RuleBaseError(f"{name}: rule {r['id']}: effect must be allow or deny")
            tagged = r.get("entity", self.root.name)
            tagged = [tagged] if isinstance(tagged, str) else list(tagged)
            for ent_name in tagged:
                if ent_name not in self.entities:
                    raise RuleBaseError(f"{name}: rule {r['id']}: unknown entity {ent_name!r}")
                if (r["id"], ent_name) in seen_pairs:
                    raise RuleBaseError(f"{name}: rule {r['id']}: entity {ent_name!r} listed twice")
                seen_pairs.add((r["id"], ent_name))
                try:
                    when = conditions.parse(
                        r["when"], self.entities[ent_name].vocabulary)
                except conditions.ConditionError as e:
                    raise RuleBaseError(
                        f"{name}: rule {r['id']} (entity {ent_name}): {e}") from e
                parsed.append(Rule(r["id"], r.get("description", ""),
                                   r["effect"], ent_name, when))
        self.rules = tuple(parsed)

    # -- per-entity views ---------------------------------------------------

    def entity_of(self, entity=None):
        """The Entity spec for a name (None = the root)."""
        if entity is None:
            return self.root
        try:
            return self.entities[entity]
        except KeyError:
            raise RuleBaseError(f"{self.name}: unknown entity {entity!r}") from None

    def rules_for(self, entity=None):
        ent = self.entity_of(entity).name
        return tuple(r for r in self.rules if r.entity == ent)

    def assumptions_for(self, entity=None):
        """Assumptions re-parsed in this entity's vocabulary (an assumption
        that references root-only variables simply doesn't apply here)."""
        ent = self.entity_of(entity)
        if ent is self.root:
            return self.assumptions
        out = []
        for aid, desc, src in self._assumption_docs:
            try:
                out.append(Assumption(aid, desc,
                                      conditions.parse(src, ent.vocabulary)))
            except conditions.ConditionError:
                pass
        return tuple(out)

    # -- decision -------------------------------------------------------------

    def decide(self, situation, entity=None):
        """Returns the deciding Rule; effect 'deny' means the request is
        refused. Only rules tagged for `entity` (default: the root) apply."""
        applicable = [r for r in self.rules_for(entity)
                      if r.when.evaluate(situation)]
        for r in applicable:
            if r.effect == "deny":
                return r
        for r in applicable:
            if r.effect == "allow":
                return r
        return DEFAULT_DENY

    # -- root-entity views: a single-entity rule base (and every app written
    # -- against one) sees exactly the pre-multi-entity API ------------------

    @property
    def entity(self):
        return self.root.name

    @property
    def states(self):
        return self.root.states

    @property
    def fields(self):
        return self.root.fields

    @property
    def has_fields(self):
        return self.root.has_fields

    @property
    def transitions(self):
        return self.root.transitions

    @property
    def actions(self):
        return self.root.actions

    @property
    def projections(self):
        return self.root.projections

    @property
    def vocabulary(self):
        return self.root.vocabulary

    def transition_for(self, action, state=None):
        return self.root.transition_for(action, state)

    def creating_transition(self):
        return self.root.creating_transition()

    def lifecycle_legal(self, action, state):
        return self.root.lifecycle_legal(action, state)

    def situation(self, *args, **kwargs):
        return self.root.situation(*args, **kwargs)

    def all_situations(self):
        return self.root.all_situations()


def _project(projection, value, today, actor_attrs):
    """Compute a declared projection from a concrete field value. ISO date
    strings compare correctly as strings, so no parsing is needed. An empty
    field or empty actor attribute never matches anything."""
    if projection.kind == "date_passed":
        return bool(value) and today is not None and str(value) < str(today)
    if projection.kind == "actor_matches_field":
        attr = actor_attrs.get(projection.actor_attr)
        return bool(value) and bool(attr) and str(value) == str(attr)
    raise AssertionError(projection.kind)


def load(path):
    path = pathlib.Path(path)
    with open(path) as f:
        doc = yaml.safe_load(f)
    return RuleBase(doc, name=str(path))
