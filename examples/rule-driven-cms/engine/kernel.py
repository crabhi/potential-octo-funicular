"""The verified boundary, as a class/function-level API (guardrail 10).

Everything above this module is FREE: apps hand-write their own UI (htmx,
anything) and customize the UX without limit. Everything below it is
GUARDED: every read and every mutation is decided by the rule base before
it touches the store, and a refusal is a typed `Denied` carrying the rule
that refused — the same vocabulary the analyzer, the gate files and the
tickets use. The UI is a client of the kernel, never an enforcement point:
hiding a button changes nothing about what the kernel permits.

    from engine import kernel

    k = kernel.boot("rulesets/helpdesk", "app.db",
                    today="2026-08-14", seed="rulesets/helpdesk/features.yaml")
    rows  = k.visible(actor)                     # the read rule, applied
    row   = k.create(actor, {"subject": "hi"})   # decided, then stored
    row   = k.act(actor, "resolve", row["id"])   # lifecycle transition
    row   = k.edit(actor, row["id"], {"subject": "hey"})
    d     = k.decide(actor, "close", row)        # pure query, for affordances
    try: k.delete(actor, row["id"])
    except kernel.Denied as e: e.rule.id         # 'nothing_is_deleted'

App code imports THIS MODULE ONLY — not the store, not sqlite3, not the
server. The boundary is held mechanically by `python -m analysis.boundary
<app dir>` (run it in the app's check.sh), and the connection is
name-mangled so reaching around the kernel is loud in review, not quiet.

Edits are decided TWICE: once on the current row (may this actor edit this
thing?) and once on the row with the updates applied (may the thing become
this?). The second decision closes the "edit is blind to proposed values"
gap of research note 14 — e.g. re-tenanting a resource by editing its org
field is refused by the same tenancy rule that guards reads.
"""

import collections

from . import features as features_mod
from . import rulebase as rb_mod
from . import store

Actor = features_mod.Actor
ANONYMOUS = features_mod.ANONYMOUS

Decision = collections.namedtuple("Decision", "allowed rule situation")
"""A pure decision: `allowed` bool, `rule` the deciding Rule (the granting
allow or the refusing deny; None when the lifecycle makes the action
structurally impossible), `situation` the vocabulary the rule saw."""


class Denied(Exception):
    """A refusal, as a value: .rule names the denying rule (its .id is the
    shared vocabulary; .description is the stakeholder sentence)."""

    def __init__(self, rule, situation):
        super().__init__(f"denied by {rule.id}")
        self.rule = rule
        self.situation = situation


class Illegal(Exception):
    """Structurally impossible: the lifecycle has no such action from the
    resource's current state. Not a policy refusal — a shape error."""

    def __init__(self, action, state):
        super().__init__(f"cannot {action} in state {state!r}")
        self.action = action
        self.state = state


def evaluate(rb, actor, action, row, today, new_fields=None):
    """The one decision path: structural lifecycle check, then the rule
    decision. Returns (status, verdict, situation) with status 'illegal'
    or 'ok'. `row` is any mapping with author, state and the fields;
    `new_fields` is the create path (no row exists yet)."""
    state = row["state"] if row is not None else rb_mod.NO_STATE
    if not rb.lifecycle_legal(action, state):
        return "illegal", None, None
    fields = new_fields if row is None else {f: row[f] for f in rb.fields}
    is_author = True if row is None else actor.name == row["author"]
    situation = rb.situation(actor.role, actor.active, is_author, action, state,
                             fields, today=today,
                             actor_attrs=features_mod.actor_attrs(actor))
    return "ok", rb.decide(situation), situation


class Kernel:
    """The only path to application state. Construct once (or via boot());
    every method decides through the rule base before touching the store."""

    def __init__(self, rb, conn, clock=None):
        self.rb = rb
        self.__conn = conn
        self.__clock = clock if clock is not None else {}

    # -- clock (engine state: date projections read it) ------------------------
    @property
    def today(self):
        return self.__clock.get("today")

    def set_today(self, iso_date):
        self.__clock["today"] = str(iso_date)

    # -- identity ---------------------------------------------------------------
    def actor(self, name):
        """The named account as an Actor, or None. No name = ANONYMOUS."""
        if not name:
            return ANONYMOUS
        row = store.get_user(self.__conn, name)
        if row is None:
            return None
        return Actor(row["name"], row["role"], bool(row["active"]),
                     {f: row[f] for f in self.rb.actor_fields})

    def users(self):
        return [Actor(r["name"], r["role"], bool(r["active"]),
                      {f: r[f] for f in self.rb.actor_fields})
                for r in store.list_users(self.__conn)]

    # -- pure decisions (no mutation; UIs build affordances from these) ---------
    def decide(self, actor, action, row=None, new_fields=None):
        status, verdict, situation = evaluate(
            self.rb, actor, action, row, self.today, new_fields)
        if status == "illegal":
            return Decision(False, None, None)
        return Decision(verdict.effect == "allow", verdict, situation)

    def affordances(self, actor, row):
        """Every structurally-legal action on this row (read excluded),
        with its Decision — enough to render buttons, or to hide them, or
        anything else: the presentation is the client's business."""
        return [(a, self.decide(actor, a, row)) for a in self.rb.actions
                if a != "read" and self.rb.lifecycle_legal(a, row["state"])]

    # -- reads -------------------------------------------------------------------
    def visible(self, actor):
        """All rows this actor's read decision allows — the list IS the rule."""
        return [r for r in store.list_items(self.__conn)
                if self.decide(actor, "read", r).allowed]

    def get(self, actor, item_id):
        """One row, read-decided: None if it does not exist, Denied if it
        exists but the rules refuse this actor the read."""
        row = store.get_item(self.__conn, int(item_id))
        if row is None:
            return None
        self.__require(actor, "read", row)
        return row

    # -- mutations (decide, then store; never the other way around) --------------
    def create(self, actor, fields):
        t = self.rb.creating_transition()
        fields = {f: str((fields or {}).get(f, "")) for f in self.rb.fields}
        self.__require(actor, t.action, None, new_fields=fields)
        item_id = store.create_item(self.__conn, self.rb, actor.name,
                                    t.target, fields)
        return store.get_item(self.__conn, item_id)

    def act(self, actor, action, item_id):
        """A declared lifecycle transition (create has its own method)."""
        row = self.__row(item_id)
        t = self.rb.transition_for(action, row["state"])
        if t is None or t.source == rb_mod.NO_STATE:
            raise Illegal(action, row["state"])
        self.__require(actor, action, row)
        store.update_item(self.__conn, self.rb, row["id"], {"state": t.target})
        return store.get_item(self.__conn, row["id"])

    def edit(self, actor, item_id, updates):
        row = self.__row(item_id)
        updates = {f: str(v) for f, v in (updates or {}).items()
                   if f in self.rb.fields}
        self.__require(actor, "edit", row)          # may they edit this?
        after = {f: row[f] for f in self.rb.fields}
        after.update(updates)
        after["state"], after["author"] = row["state"], row["author"]
        self.__require(actor, "edit", after)        # may it BECOME this?
        store.update_item(self.__conn, self.rb, row["id"], updates)
        return store.get_item(self.__conn, row["id"])

    def delete(self, actor, item_id):
        row = self.__row(item_id)
        self.__require(actor, "delete", row)
        store.delete_item(self.__conn, row["id"])

    # -- internal -----------------------------------------------------------------
    def __row(self, item_id):
        row = store.get_item(self.__conn, int(item_id))
        if row is None:
            raise KeyError(item_id)
        return row

    def __require(self, actor, action, row, new_fields=None):
        status, verdict, situation = evaluate(
            self.rb, actor, action, row, self.today, new_fields)
        if status == "illegal":
            state = row["state"] if row is not None else rb_mod.NO_STATE
            raise Illegal(action, state)
        if verdict.effect == "deny":
            raise Denied(verdict, situation)


def boot(rules_dir, db_path, today=None, seed=None):
    """One-call construction for apps: load the rule base, open the store
    (seeding user accounts from a features.yaml), return the Kernel. This
    is the app's ONLY doorway to state — rules_dir decides everything."""
    rb = rb_mod.load(f"{rules_dir}/rules.yaml")
    actors = features_mod.load(seed)[0] if seed else None
    conn = store.open_db(str(db_path), rb, actors)
    return Kernel(rb, conn, {"today": today} if today else {})
