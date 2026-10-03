"""REVIEWED — the kernel: the only owner of Relay's state.

Every read and write is decided by the guard rules (relay.policy, with the
rules of relay.cases and relay.thread registered) over the transition tables
before the store is touched; refusals come back as `Denied` values.

`DeskReader` is the kernel as one actor sees it, read-only — the object
capability black boxes receive. `ActorView` implements it; the sandbox can
call exactly the protocol's methods and nothing else. Nothing generated
can reach the store: boxes read through DeskReader and return values;
only reviewed code (relay.web.server, relay.mail.gateway) writes.
"""

from __future__ import annotations

import dataclasses
import threading
from datetime import date
from typing import Protocol, get_args

import relay.cases.rules  # noqa: F401  (registers the case rules)
import relay.thread.rules  # noqa: F401  (registers the thread rules)
from relay.cases.model import (CASE_INITIAL, CASE_TRANSITIONS, Case, CaseAction, CaseDraft,
                               CasePatch)
from relay.people import ANONYMOUS, Actor
from relay.policy import POLICY, Affordance, Denied, Situation, lifecycle_refusal
from relay.thread.model import (ATTACHMENT_INITIAL, ATTACHMENT_TRANSITIONS, COMMENT_INITIAL,
                                COMMENT_TRANSITIONS, Attachment, AttachmentAction,
                                AttachmentDraft, Comment, CommentAction, CommentDraft)


class DeskReader(Protocol):
    """The kernel, read-only, as the current viewer sees it. Every list is
    already filtered by the read rules (an internal note simply is not in a
    customer's thread; a redacted comment arrives with an empty body)."""

    def me(self) -> Actor: ...
    def today(self) -> date: ...
    def people(self) -> list[Actor]: ...
    def cases(self) -> list[Case]: ...
    def case(self, case_id: int) -> Case | Denied | None: ...
    def thread(self, case_id: int) -> list[Comment]: ...
    def evidence(self, case_id: int) -> list[Attachment]: ...
    def case_actions(self, case_id: int) -> list[Affordance]: ...
    def may_edit(self, case_id: int) -> Affordance: ...
    def may_post(self, case_id: int, internal: bool) -> Affordance: ...
    def may_attach(self, case_id: int) -> Affordance: ...
    def comment_actions(self, comment_id: int) -> list[Affordance]: ...
    def attachment_actions(self, attachment_id: int) -> list[Affordance]: ...


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
        if action in get_args(CaseAction) and (case.state, action) not in CASE_TRANSITIONS:
            return lifecycle_refusal("case", action, case.state)
        return POLICY.decide("case", Situation(actor, action, case, self.today))

    def decide_comment(self, actor: Actor, action: str, case: Case,
                       comment: Comment) -> Denied | None:
        if action in get_args(CommentAction) and (comment.state, action) not in COMMENT_TRANSITIONS:
            return lifecycle_refusal("comment", action, comment.state)
        return POLICY.decide("comment", Situation(actor, action, case, self.today,
                                                  comment=comment))

    def decide_attachment(self, actor: Actor, action: str, case: Case,
                          att: Attachment) -> Denied | None:
        if action in get_args(AttachmentAction) and (att.state, action) not in ATTACHMENT_TRANSITIONS:
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
                       org=draft.org.strip(), requester=actor.name, state=CASE_INITIAL,
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
            if action not in get_args(CaseAction):
                return lifecycle_refusal("case", action, case.state)
            refused = self.decide_case(actor, action, case)
            if refused:
                return refused
            new = dataclasses.replace(case, state=CASE_TRANSITIONS[(case.state, action)])
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
                          internal=draft.internal, state=COMMENT_INITIAL)
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
            if action not in get_args(CommentAction):
                return lifecycle_refusal("comment", action, c.state)
            refused = self.decide_comment(actor, action, self._cases[c.case_id], c)
            if refused:
                return refused
            new = dataclasses.replace(c, state=COMMENT_TRANSITIONS[(c.state, action)])
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
                             state=ATTACHMENT_INITIAL)
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
            if action not in get_args(AttachmentAction):
                return lifecycle_refusal("attachment", action, a.state)
            refused = self.decide_attachment(actor, action, self._cases[a.case_id], a)
            if refused:
                return refused
            new = dataclasses.replace(a, state=ATTACHMENT_TRANSITIONS[(a.state, action)])
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
                for (s, a) in CASE_TRANSITIONS if s == case.state]

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
                for (s, a) in COMMENT_TRANSITIONS if s == c.state]

    def attachment_actions(self, attachment_id: int) -> list[Affordance]:
        d = self._desk
        a = d._attachments.get(attachment_id)
        if a is None or a.id not in {x.id for x in self.evidence(a.case_id)}:
            return []
        case = d._cases[a.case_id]
        return [_afford(x, d.decide_attachment(self._actor, x, case, a))
                for (s, x) in ATTACHMENT_TRANSITIONS if s == a.state]

    def _readable(self, case_id: int) -> Case | None:
        got = self._desk.get_case(self._actor, case_id)
        return got if isinstance(got, Case) else None
