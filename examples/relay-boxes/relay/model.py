"""REVIEWED — the data model of Relay (see ../TICKETS.md, HD-1…HD-9).

Plain frozen dataclasses and closed vocabularies. These are the only
shapes that cross between reviewed code and generated black boxes; the
sandbox can read them, and can construct them only where a box's
contract names them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Role = Literal["anonymous", "customer", "agent", "lead", "mailbot"]
Severity = Literal["high", "med", "low"]

CaseState = Literal["new", "open", "waiting", "resolved", "closed"]
CaseAction = Literal["triage", "wait", "reply", "resolve", "reopen", "close"]
CommentState = Literal["posted", "redacted"]
CommentAction = Literal["redact"]
AttachmentState = Literal["attached", "removed"]
AttachmentAction = Literal["remove"]


@dataclass(frozen=True)
class Actor:
    """Someone (or something) using Relay. Staff and the robot have no org."""
    name: str
    role: Role
    org: str | None = None
    active: bool = True


@dataclass(frozen=True)
class Case:
    """HD-2: a support case, opened by `requester` inside `org`."""
    id: int
    subject: str
    org: str
    requester: str
    state: CaseState
    severity: Severity
    assignee: str | None
    sla_due: date | None


@dataclass(frozen=True)
class Comment:
    """HD-8: one entry in a case's thread. Never edited; a redaction keeps
    the tombstone (state "redacted", body withheld)."""
    id: int
    case_id: int
    author: str
    body: str
    internal: bool
    state: CommentState


@dataclass(frozen=True)
class Attachment:
    """HD-9: evidence on a case. Removal keeps the tombstone."""
    id: int
    case_id: int
    author: str
    filename: str
    state: AttachmentState


@dataclass(frozen=True)
class Denied:
    """A refusal, as a value: the rule that refused and its description."""
    rule: str
    reason: str


# -- what callers hand the kernel to create or change things -----------------

@dataclass(frozen=True)
class CaseDraft:
    subject: str
    org: str
    severity: Severity
    sla_due: date | None


@dataclass(frozen=True)
class CasePatch:
    """Fields to change on a case; None leaves a field as it is. An empty
    `assignee` string unassigns."""
    subject: str | None = None
    org: str | None = None
    severity: Severity | None = None
    assignee: str | None = None
    sla_due: date | None = None


@dataclass(frozen=True)
class CommentDraft:
    body: str
    internal: bool


@dataclass(frozen=True)
class AttachmentDraft:
    filename: str


@dataclass(frozen=True)
class Affordance:
    """Whether `actor` may perform `action` right now, and if not, why."""
    action: str
    allowed: bool
    rule: str | None
    reason: str | None
