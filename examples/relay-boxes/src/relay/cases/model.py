"""REVIEWED — the case (HD-2…HD-5) and what callers hand the kernel to
create or change one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Severity = Literal["high", "med", "low"]

CaseState = Literal["new", "open", "waiting", "resolved", "closed"]
CaseAction = Literal["triage", "wait", "reply", "resolve", "reopen", "close"]


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
