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

CHILD ENTITIES (comments, attachments — anything context-sensitive): the
same calls take an `entity=` name, creation takes the parent's id, and the
kernel joins the live parent row into every decision — the client never
computes context, so it can never compute it wrong:

    note = k.create(actor, {"body": "internal note", "internal": "yes"},
                    entity="comment", parent_id=case["id"])
    k.visible(actor, entity="comment", parent_id=case["id"])   # the thread
    k.act(actor, "redact", note["id"], entity="comment")
    # a closed case seals its thread: parent.state is in the situation
    # the rules decide on — the deny names the rule, as always

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


def evaluate(rb, actor, action, row, today, new_fields=None,
             entity=None, parent_row=None):
    """The one decision path: structural lifecycle check, then the rule
    decision. Returns (status, verdict, situation) with status 'illegal'
    or 'ok'. `row` is any mapping with author, state and the fields;
    `new_fields` is the create path (no row exists yet). For a child
    entity, `parent_row` is the live parent — its state and projections
    are the context the rules decide on."""
    ent = rb.entity_of(entity)
    state = row["state"] if row is not None else rb_mod.NO_STATE
    if not ent.lifecycle_legal(action, state):
        return "illegal", None, None
    fields = new_fields if row is None else {f: row[f] for f in ent.fields}
    is_author = True if row is None else actor.name == row["author"]
    situation = ent.situation(actor.role, actor.active, is_author, action, state,
                              fields, today=today,
                              actor_attrs=features_mod.actor_attrs(actor),
                              parent=parent_row)
    return "ok", rb.decide(situation, entity=ent.name), situation


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
    def decide(self, actor, action, row=None, new_fields=None,
               entity=None, parent=None):
        """For a child entity, `parent` is the parent row or its id; when
        omitted and `row` is a stored child, the kernel joins the parent
        itself (the client never has to)."""
        ent = self.rb.entity_of(entity)
        parent_row = self.__parent_row(ent, row, parent)
        status, verdict, situation = evaluate(
            self.rb, actor, action, row, self.today, new_fields,
            entity=ent.name, parent_row=parent_row)
        if status == "illegal":
            return Decision(False, None, None)
        return Decision(verdict.effect == "allow", verdict, situation)

    def affordances(self, actor, row, entity=None):
        """Every structurally-legal action on this row (read excluded),
        with its Decision — enough to render buttons, or to hide them, or
        anything else: the presentation is the client's business."""
        ent = self.rb.entity_of(entity)
        parent_row = self.__parent_row(ent, row, None)
        return [(a, self.decide(actor, a, row, entity=ent.name, parent=parent_row))
                for a in ent.actions
                if a != "read" and ent.lifecycle_legal(a, row["state"])]

    # -- reads -------------------------------------------------------------------
    def visible(self, actor, entity=None, parent_id=None):
        """All rows this actor's read decision allows — the list IS the
        rule. For a child entity, pass parent_id to list one thread; the
        kernel joins each row's parent into the read decision either way."""
        ent = self.rb.entity_of(entity)
        parents = {}
        out = []
        for r in store.list_items(self.__conn, self.rb, ent.name, parent_id):
            parent_row = None
            if ent.parent is not None:
                pid = r["parent_id"]
                if pid not in parents:
                    parents[pid] = store.get_item(self.__conn, self.rb, pid,
                                                  ent.parent.name)
                parent_row = parents[pid]
            if self.decide(actor, "read", r, entity=ent.name,
                           parent=parent_row).allowed:
                out.append(r)
        return out

    def get(self, actor, item_id, entity=None):
        """One row, read-decided: None if it does not exist, Denied if it
        exists but the rules refuse this actor the read."""
        ent = self.rb.entity_of(entity)
        row = store.get_item(self.__conn, self.rb, int(item_id), ent.name)
        if row is None:
            return None
        self.__require(actor, "read", row, entity=ent.name)
        return row

    # -- mutations (decide, then store; never the other way around) --------------
    def create(self, actor, fields, entity=None, parent_id=None):
        ent = self.rb.entity_of(entity)
        if (parent_id is not None) != (ent.parent is not None):
            raise ValueError(f"entity {ent.name!r} "
                             + ("takes no parent_id" if ent.parent is None
                                else "needs a parent_id"))
        parent_row = None
        if ent.parent is not None:
            parent_row = store.get_item(self.__conn, self.rb, int(parent_id),
                                        ent.parent.name)
            if parent_row is None:
                raise KeyError(parent_id)
        t = ent.creating_transition()
        fields = {f: str((fields or {}).get(f, "")) for f in ent.fields}
        self.__require(actor, t.action, None, new_fields=fields,
                       entity=ent.name, parent_row=parent_row)
        item_id = store.create_item(self.__conn, self.rb, actor.name, t.target,
                                    fields, entity=ent.name, parent_id=parent_id)
        return store.get_item(self.__conn, self.rb, item_id, ent.name)

    def act(self, actor, action, item_id, entity=None):
        """A declared lifecycle transition (create has its own method)."""
        ent = self.rb.entity_of(entity)
        row = self.__row(item_id, ent)
        t = ent.transition_for(action, row["state"])
        if t is None or t.source == rb_mod.NO_STATE:
            raise Illegal(action, row["state"])
        self.__require(actor, action, row, entity=ent.name)
        store.update_item(self.__conn, self.rb, row["id"], {"state": t.target},
                          entity=ent.name)
        return store.get_item(self.__conn, self.rb, row["id"], ent.name)

    def edit(self, actor, item_id, updates, entity=None):
        ent = self.rb.entity_of(entity)
        row = self.__row(item_id, ent)
        updates = {f: str(v) for f, v in (updates or {}).items()
                   if f in ent.fields}
        parent_row = self.__parent_row(ent, row, None)
        self.__require(actor, "edit", row, entity=ent.name,
                       parent_row=parent_row)          # may they edit this?
        after = {f: row[f] for f in ent.fields}
        after.update(updates)
        after["state"], after["author"] = row["state"], row["author"]
        self.__require(actor, "edit", after, entity=ent.name,
                       parent_row=parent_row)          # may it BECOME this?
        store.update_item(self.__conn, self.rb, row["id"], updates,
                          entity=ent.name)
        return store.get_item(self.__conn, self.rb, row["id"], ent.name)

    def delete(self, actor, item_id, entity=None):
        ent = self.rb.entity_of(entity)
        row = self.__row(item_id, ent)
        self.__require(actor, "delete", row, entity=ent.name)
        store.delete_item(self.__conn, self.rb, row["id"], entity=ent.name)

    # -- internal -----------------------------------------------------------------
    def __row(self, item_id, ent):
        row = store.get_item(self.__conn, self.rb, int(item_id), ent.name)
        if row is None:
            raise KeyError(item_id)
        return row

    def __parent_row(self, ent, row, parent):
        """Resolve the parent row for a child-entity decision: an explicit
        row mapping, an explicit id, or the stored row's own parent_id."""
        if ent.parent is None:
            return None
        if parent is not None and not isinstance(parent, int):
            return parent
        pid = parent
        if pid is None and row is not None and "parent_id" in row.keys():
            pid = row["parent_id"]
        if pid is None:
            return None
        return store.get_item(self.__conn, self.rb, int(pid), ent.parent.name)

    def __require(self, actor, action, row, new_fields=None,
                  entity=None, parent_row=None):
        ent = self.rb.entity_of(entity)
        if ent.parent is not None and parent_row is None:
            parent_row = self.__parent_row(ent, row, None)
        status, verdict, situation = evaluate(
            self.rb, actor, action, row, self.today, new_fields,
            entity=ent.name, parent_row=parent_row)
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
