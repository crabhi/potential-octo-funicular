"""REVIEWED — comments (HD-8) and attachments (HD-9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommentState = Literal["posted", "redacted"]
CommentAction = Literal["redact"]
AttachmentState = Literal["attached", "removed"]
AttachmentAction = Literal["remove"]


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
class CommentDraft:
    body: str
    internal: bool


@dataclass(frozen=True)
class AttachmentDraft:
    filename: str
