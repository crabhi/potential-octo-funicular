"""REVIEWED — Relay's state transitions, guard rules and the kernel.

Three things live here, all human-reviewed:

  1. LIFECYCLES — the state machines of case, comment and attachment;
  2. POLICY — who may do what, as named deny/allow rules (ids and
     wording kept from the rule-engine Relay so the two compare 1:1);
  3. Desk — the kernel: the only owner of state. Every read and write is
     decided by POLICY over LIFECYCLES before the store is touched;
     refusals are `Denied` values naming the rule. `ActorView` is the
     read-only, actor-bound face of the kernel that black boxes receive
     as their `DeskReader` capability.

Nothing generated runs in this file, and nothing generated can reach the
store: boxes get `ActorView` (reads, decided per actor) and return
values; only the reviewed shell turns those values into kernel writes.
"""

from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass
from datetime import date

from boxkit import Lifecycle, Policy, T

from .model import (Actor, Affordance, Attachment, AttachmentDraft,
                    AttachmentState, Case, CaseDraft, CasePatch, CaseState,
                    Comment, CommentDraft, CommentState, Denied)

# ---------------------------------------------------------------------------
# 1. Lifecycles

CASE = Lifecycle("case", CaseState, initial="new", terminal=("closed",), transitions=[
    T("triage",  "new",      "open"),       # HD-3
    T("wait",    "open",     "waiting"),    # HD-3
    T("reply",   "waiting",  "open"),       # HD-3: a customer reply pulls it back
    T("resolve", "open",     "resolved"),   # HD-4/5
    T("reopen",  "resolved", "open"),       # HD-4: the requester disputes
    T("close",   "resolved", "closed"),     # HD-6: the QA step
])

COMMENT = Lifecycle("comment", CommentState, initial="posted",
                    terminal=("redacted",), transitions=[
    T("redact", "posted", "redacted"),      # HD-8: the tombstone stays
])

ATTACHMENT = Lifecycle("attachment", AttachmentState, initial="attached",
                       terminal=("removed",), transitions=[
    T("remove", "attached", "removed"),     # HD-9: the tombstone stays
])

# Non-transition actions per entity. There is no delete anywhere: HD-6
# ("nothing in Relay is ever deleted") holds because no such method exists.
CASE_ACTIONS = ("open", "read", "edit", *CASE.actions)
COMMENT_ACTIONS = ("post", "read", *COMMENT.actions)
ATTACHMENT_ACTIONS = ("attach", "read", *ATTACHMENT.actions)


# ---------------------------------------------------------------------------
# 2. Policy

@dataclass(frozen=True)
class Situation:
    """Everything a rule may look at. For thread/evidence decisions `case`
    is the live PARENT case — the kernel joins it in, never the caller."""
    actor: Actor
    action: str
    case: Case
    today: date
    comment: Comment | None = None
    attachment: Attachment | None = None

    @property
    def staff(self) -> bool:
        return self.actor.role in ("agent", "lead")

    @property
    def same_org(self) -> bool:
        return self.actor.org is not None and self.actor.org == self.case.org

    @property
    def mine(self) -> bool:
        return self.case.assignee is not None and self.case.assignee == self.actor.name

    @property
    def breached(self) -> bool:
        return self.case.sla_due is not None and self.case.sla_due < self.today


POLICY: Policy[Situation, Denied] = Policy(Denied)
ALL = ("case", "comment", "attachment")
CHILDREN = ("comment", "attachment")

# ---- denies ----

@POLICY.deny("deny_inactive", "A deactivated account can do nothing at all.", on=ALL)
def _(s: Situation) -> bool:
    return not s.actor.active

@POLICY.deny("org_walls", """HD-1: customers see and touch only their own
    organization's cases — reading included, and a case can never be moved
    into or out of an organization by its customers.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and not s.same_org

@POLICY.deny("case_needs_subject", """HD-2: no case without a subject — a
    subjectless case cannot be triaged, routed or reported on.""", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "open" and not s.case.subject.strip()

@POLICY.deny("only_assignee_resolves", """HD-4: a case is resolved by the agent
    it is assigned to; only a lead may resolve someone else's case.""", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and not s.mine and s.actor.role != "lead"

@POLICY.deny("breach_needs_lead", """HD-5: once the SLA is breached, an ordinary
    agent may no longer resolve the case — every breach gets senior eyes.""",
    on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and s.breached and s.actor.role != "lead"

@POLICY.deny("sealed_after_resolution", """HD-2 + HD-6: a resolved or closed case
    is no longer editable, by anyone — reopen it (customers) or live with the
    record.""", on=("case",))
def _(s: Situation) -> bool:
    return s.case.state in ("resolved", "closed") and s.action == "edit"

@POLICY.deny("org_walls_thread", """HD-1 via HD-8/9: the org wall extends to a
    case's thread and evidence — the PARENT case's org decides.""", on=CHILDREN)
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and not s.same_org

@POLICY.deny("sealed_thread", """HD-8/9 + HD-6: a closed case seals its thread
    and its evidence — nothing new is said, redacted, attached or removed; the
    record stays readable forever.""", on=CHILDREN)
def _(s: Situation) -> bool:
    return s.case.state == "closed" and s.action != "read"

@POLICY.deny("comment_needs_body", "HD-8: a comment needs a body.", on=("comment",))
def _(s: Situation) -> bool:
    return s.action == "post" and s.comment is not None and not s.comment.body.strip()

@POLICY.deny("internal_is_staff_only", """HD-8: internal notes never reach
    customers or the robot — not readable, not postable, not anything.""",
    on=("comment",))
def _(s: Situation) -> bool:
    return s.comment is not None and s.comment.internal and not s.staff

@POLICY.deny("fresh_evidence_only", """HD-9: a resolved or closed case takes no
    new evidence — dispute the resolution first.""", on=("attachment",))
def _(s: Situation) -> bool:
    return s.action == "attach" and s.case.state in ("resolved", "closed")

@POLICY.deny("attachment_needs_file", "HD-9: an attachment needs a filename.",
             on=("attachment",))
def _(s: Situation) -> bool:
    return (s.action == "attach" and s.attachment is not None
            and not s.attachment.filename.strip())

# ---- allows (silence denies: there are no "customers never triage",
# "staff never reopen", "the robot does nothing else" denies — the allows
# are tight, and tests/reviewed/test_policy.py proves each containment
# over the whole situation grid) ----

@POLICY.allow("customer_opens", "HD-2: customers open cases (into their own org).",
              on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "open"

@POLICY.allow("customer_follows", "HD-1: everyone in the customer org follows "
              "the org's cases.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "read"

@POLICY.allow("customer_edits", """HD-2: customers maintain their org's cases
    while they are being worked.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "edit"

@POLICY.allow("customer_replies", "HD-3: a customer reply pulls a waiting case "
              "back into the working queue.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "reply"

@POLICY.allow("customer_reopens", "HD-4: the requester's side decides whether it "
              "is fixed — customers reopen resolved cases.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "reopen"

@POLICY.allow("staff_serve", """HD-3: staff work every org's cases: read, edit,
    open (a case taken by phone), triage, put on hold, resolve.""", on=("case",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "edit", "open", "triage", "wait", "resolve")

@POLICY.allow("lead_closes", "HD-6: closing is the QA step, and it is a lead's.",
              on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "close"

@POLICY.allow("mailbot_files", """HD-7: the mail robot opens cases from inbound
    email and files customer replies — its entire blast radius.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action in ("open", "reply")

@POLICY.allow("customer_discusses", "HD-8: customers read and join their org's "
              "case threads.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action in ("read", "post")

@POLICY.allow("staff_discuss", "HD-8: staff read and join every thread, internal "
              "notes included.", on=("comment",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "post")

@POLICY.allow("lead_redacts", "HD-8: if something must disappear, a lead redacts "
              "it — and the redaction stays on the record.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "redact"

@POLICY.allow("mailbot_files_mail", "HD-8: the robot files inbound email bodies "
              "as comments — it never reads the thread back.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action == "post"

@POLICY.allow("customer_attaches", "HD-9: customers read and add their org's "
              "evidence.", on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action in ("read", "attach")

@POLICY.allow("staff_attach", "HD-9: staff read and add evidence on every case.",
              on=("attachment",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "attach")

@POLICY.allow("author_removes", "HD-9: a mistaken upload is removed by the person "
              "who attached it (removal keeps the tombstone).", on=("attachment",))
def _(s: Situation) -> bool:
    return (s.action == "remove" and s.attachment is not None
            and s.attachment.author == s.actor.name
            and s.actor.role in ("customer", "agent", "lead"))

@POLICY.allow("lead_removes", "HD-9: a lead removes anyone's mistaken upload.",
              on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "remove"

@POLICY.allow("mailbot_attaches", "HD-9: the robot files email attachments — and "
              "never removes or reads anything.", on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action == "attach"


def lifecycle_refusal(entity: str, action: str, state: str) -> Denied:
    return Denied("lifecycle", f"A {entity} in state '{state}' has no '{action}'.")


# ---------------------------------------------------------------------------
# 3. The kernel

ANONYMOUS = Actor("anonymous", "anonymous")


class Desk:
    """The only owner of Relay's state. Every method decides before it
    touches the store; refusals come back as `Denied` values."""

    def __init__(self, today: date, people: list[Actor]):
        self.today = today
        self._people = {p.name: p for p in people}
        self._cases: dict[int, Case] = {}
        self._comments: dict[int, Comment] = {}
        self._attachments: dict[int, Attachment] = {}
        self._ids = {"case": 0, "comment": 0, "attachment": 0}
        self._lock = threading.RLock()

    # -- who ------------------------------------------------------------------
    def actor(self, name: str | None) -> Actor:
        return self._people.get(name or "", ANONYMOUS)

    def people(self) -> list[Actor]:
        return list(self._people.values())

    def view(self, actor: Actor) -> ActorView:
        return ActorView(self, actor)

    def org_of_case(self, case_id: int) -> str | None:
        """System lookup for the mail gateway (shell.py), which must check a
        reply's sender against the case's org although the robot itself
        can read nothing (HD-7). Never exposed to black boxes."""
        with self._lock:
            case = self._cases.get(case_id)
            return case.org if case else None

    # -- pure decisions ---------------------------------------------------------
    def decide_case(self, actor: Actor, action: str, case: Case) -> Denied | None:
        if action in CASE.actions and CASE.step(case.state, action) is None:
            return lifecycle_refusal("case", action, case.state)
        return POLICY.decide("case", Situation(actor, action, case, self.today))

    def decide_comment(self, actor: Actor, action: str, case: Case,
                       comment: Comment) -> Denied | None:
        if action in COMMENT.actions and COMMENT.step(comment.state, action) is None:
            return lifecycle_refusal("comment", action, comment.state)
        return POLICY.decide("comment", Situation(actor, action, case, self.today,
                                                  comment=comment))

    def decide_attachment(self, actor: Actor, action: str, case: Case,
                          att: Attachment) -> Denied | None:
        if action in ATTACHMENT.actions and ATTACHMENT.step(att.state, action) is None:
            return lifecycle_refusal("attachment", action, att.state)
        return POLICY.decide("attachment", Situation(actor, action, case, self.today,
                                                     attachment=att))

    # -- reads ------------------------------------------------------------------
    def visible_cases(self, actor: Actor) -> list[Case]:
        with self._lock:
            return [c for c in self._cases.values()
                    if self.decide_case(actor, "read", c) is None]

    def get_case(self, actor: Actor, case_id: int) -> Case | Denied | None:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            return self.decide_case(actor, "read", case) or case

    def thread(self, actor: Actor, case_id: int) -> list[Comment]:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return []
            out = []
            for c in self._comments.values():
                if c.case_id == case_id and \
                        self.decide_comment(actor, "read", case, c) is None:
                    # a redaction withholds the body from everyone, here
                    out.append(dataclasses.replace(c, body="") if c.state == "redacted" else c)
            return out

    def evidence(self, actor: Actor, case_id: int) -> list[Attachment]:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return []
            return [a for a in self._attachments.values() if a.case_id == case_id
                    and self.decide_attachment(actor, "read", case, a) is None]

    # -- writes -----------------------------------------------------------------
    def open_case(self, actor: Actor, draft: CaseDraft) -> Case | Denied:
        with self._lock:
            row = Case(id=self._ids["case"] + 1, subject=draft.subject.strip(),
                       org=draft.org.strip(), requester=actor.name, state=CASE.initial,
                       severity=draft.severity, assignee=None, sla_due=draft.sla_due)
            refused = self.decide_case(actor, "open", row)
            if refused:
                return refused
            self._ids["case"] = row.id
            self._cases[row.id] = row
            return row

    def move_case(self, actor: Actor, case_id: int, action: str) -> Case | Denied | None:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            if action not in CASE.actions:
                return lifecycle_refusal("case", action, case.state)
            refused = self.decide_case(actor, action, case)
            if refused:
                return refused
            new = dataclasses.replace(case, state=CASE.step(case.state, action))
            self._cases[case_id] = new
            return new

    def edit_case(self, actor: Actor, case_id: int, patch: CasePatch) -> Case | Denied | None:
        """Decided twice: on the case as it is AND as it would become — so a
        customer cannot move a case out of (or into) their org."""
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            changes = {k: v for k, v in dataclasses.asdict(patch).items() if v is not None}
            if "assignee" in changes:
                changes["assignee"] = changes["assignee"].strip() or None
            for k in ("subject", "org"):
                if k in changes:
                    changes[k] = changes[k].strip()
            new = dataclasses.replace(case, **changes)
            refused = (self.decide_case(actor, "edit", case)
                       or self.decide_case(actor, "edit", new))
            if refused:
                return refused
            self._cases[case_id] = new
            return new

    def post_comment(self, actor: Actor, case_id: int,
                     draft: CommentDraft) -> Comment | Denied | None:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            row = Comment(id=self._ids["comment"] + 1, case_id=case_id,
                          author=actor.name, body=draft.body.strip(),
                          internal=draft.internal, state=COMMENT.initial)
            refused = self.decide_comment(actor, "post", case, row)
            if refused:
                return refused
            self._ids["comment"] = row.id
            self._comments[row.id] = row
            return row

    def act_on_comment(self, actor: Actor, comment_id: int,
                       action: str) -> Comment | Denied | None:
        with self._lock:
            c = self._comments.get(comment_id)
            if c is None:
                return None
            if action not in COMMENT.actions:
                return lifecycle_refusal("comment", action, c.state)
            refused = self.decide_comment(actor, action, self._cases[c.case_id], c)
            if refused:
                return refused
            new = dataclasses.replace(c, state=COMMENT.step(c.state, action))
            self._comments[comment_id] = new
            return new

    def attach(self, actor: Actor, case_id: int,
               draft: AttachmentDraft) -> Attachment | Denied | None:
        with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return None
            row = Attachment(id=self._ids["attachment"] + 1, case_id=case_id,
                             author=actor.name, filename=draft.filename.strip(),
                             state=ATTACHMENT.initial)
            refused = self.decide_attachment(actor, "attach", case, row)
            if refused:
                return refused
            self._ids["attachment"] = row.id
            self._attachments[row.id] = row
            return row

    def act_on_attachment(self, actor: Actor, attachment_id: int,
                          action: str) -> Attachment | Denied | None:
        with self._lock:
            a = self._attachments.get(attachment_id)
            if a is None:
                return None
            if action not in ATTACHMENT.actions:
                return lifecycle_refusal("attachment", action, a.state)
            refused = self.decide_attachment(actor, action, self._cases[a.case_id], a)
            if refused:
                return refused
            new = dataclasses.replace(a, state=ATTACHMENT.step(a.state, action))
            self._attachments[attachment_id] = new
            return new


def _afford(action: str, refused: Denied | None) -> Affordance:
    return Affordance(action, refused is None,
                      refused.rule if refused else None,
                      refused.reason if refused else None)


class ActorView:
    """The kernel as one actor sees it — read-only. Implements the
    `DeskReader` protocol black boxes receive (relay/boxes.py); the
    sandbox can call exactly the protocol's methods and nothing else."""

    def __init__(self, desk: Desk, actor: Actor):
        self._desk, self._actor = desk, actor

    def me(self) -> Actor:
        return self._actor

    def today(self) -> date:
        return self._desk.today

    def people(self) -> list[Actor]:
        return self._desk.people()

    def cases(self) -> list[Case]:
        return self._desk.visible_cases(self._actor)

    def case(self, case_id: int) -> Case | Denied | None:
        return self._desk.get_case(self._actor, case_id)

    def thread(self, case_id: int) -> list[Comment]:
        return self._desk.thread(self._actor, case_id) if self._readable(case_id) else []

    def evidence(self, case_id: int) -> list[Attachment]:
        return self._desk.evidence(self._actor, case_id) if self._readable(case_id) else []

    def case_actions(self, case_id: int) -> list[Affordance]:
        case = self._readable(case_id)
        if case is None:
            return []
        return [_afford(a, self._desk.decide_case(self._actor, a, case))
                for a in CASE.actions_from(case.state)]

    def may_edit(self, case_id: int) -> Affordance:
        case = self._readable(case_id)
        if case is None:
            return Affordance("edit", False, "default_deny", "Not visible to you.")
        return _afford("edit", self._desk.decide_case(self._actor, "edit", case))

    def may_post(self, case_id: int, internal: bool) -> Affordance:
        case = self._readable(case_id)
        if case is None:
            return Affordance("post", False, "default_deny", "Not visible to you.")
        probe = Comment(0, case_id, self._actor.name, "probe", internal, "posted")
        return _afford("post", self._desk.decide_comment(self._actor, "post", case, probe))

    def may_attach(self, case_id: int) -> Affordance:
        case = self._readable(case_id)
        if case is None:
            return Affordance("attach", False, "default_deny", "Not visible to you.")
        probe = Attachment(0, case_id, self._actor.name, "probe", "attached")
        return _afford("attach",
                       self._desk.decide_attachment(self._actor, "attach", case, probe))

    def comment_actions(self, comment_id: int) -> list[Affordance]:
        d = self._desk
        c = d._comments.get(comment_id)
        if c is None or c.id not in {x.id for x in self.thread(c.case_id)}:
            return []
        case = d._cases[c.case_id]
        return [_afford(a, d.decide_comment(self._actor, a, case, c))
                for a in COMMENT.actions_from(c.state)]

    def attachment_actions(self, attachment_id: int) -> list[Affordance]:
        d = self._desk
        a = d._attachments.get(attachment_id)
        if a is None or a.id not in {x.id for x in self.evidence(a.case_id)}:
            return []
        case = d._cases[a.case_id]
        return [_afford(x, d.decide_attachment(self._actor, x, case, a))
                for x in ATTACHMENT.actions_from(a.state)]

    def _readable(self, case_id: int) -> Case | None:
        got = self._desk.get_case(self._actor, case_id)
        return got if isinstance(got, Case) else None
