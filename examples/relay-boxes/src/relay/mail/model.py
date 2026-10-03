"""REVIEWED — inbound email and what the robot may make of it (HD-7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

from relay.cases.model import CaseDraft

OrgDirectory = Callable[[str], Union[str, None]]
"""Maps a sender address to the customer org it belongs to, or None."""


@dataclass(frozen=True)
class Email:
    sender: str
    subject: str
    body: str
    attachments: list[str]


@dataclass(frozen=True)
class MailNewCase:
    draft: CaseDraft
    body: str
    attachments: list[str]


@dataclass(frozen=True)
class MailReply:
    case_id: int
    body: str
    attachments: list[str]


@dataclass(frozen=True)
class MailBounce:
    reason: str


MailIntent = Union[MailNewCase, MailReply, MailBounce]
