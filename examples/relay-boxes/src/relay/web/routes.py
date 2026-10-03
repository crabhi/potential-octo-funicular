"""REVIEWED — what an HTTP request may mean: the typed views and commands,
and the `route` contract (body in generated.relay.web.routes). Routing
decides nothing about permission; the kernel decides when the server
applies the command."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from boxkit import blackbox
from relay.cases.model import CaseAction, CaseDraft, CasePatch
from relay.cases.queues import QueueKey
from relay.thread.model import AttachmentDraft, CommentDraft


@dataclass(frozen=True)
class HttpRequest:
    method: Literal["GET", "POST"]
    path: str
    query: dict[str, str]
    form: dict[str, str]


@dataclass(frozen=True)
class ShowQueue:
    queue: QueueKey


@dataclass(frozen=True)
class ShowCase:
    case_id: int


@dataclass(frozen=True)
class ShowNewCase:
    pass


@dataclass(frozen=True)
class OpenCase:
    draft: CaseDraft


@dataclass(frozen=True)
class EditCase:
    case_id: int
    patch: CasePatch


@dataclass(frozen=True)
class MoveCase:
    case_id: int
    action: CaseAction


@dataclass(frozen=True)
class PostComment:
    case_id: int
    draft: CommentDraft


@dataclass(frozen=True)
class RedactComment:
    case_id: int
    comment_id: int


@dataclass(frozen=True)
class AttachFile:
    case_id: int
    draft: AttachmentDraft


@dataclass(frozen=True)
class RemoveAttachment:
    case_id: int
    attachment_id: int


@dataclass(frozen=True)
class SwitchPersona:
    name: str


@dataclass(frozen=True)
class NotFound:
    pass


@dataclass(frozen=True)
class Invalid:
    message: str
    back: ShowQueue | ShowCase | ShowNewCase


Route = Union[ShowQueue, ShowCase, ShowNewCase, OpenCase, EditCase, MoveCase,
              PostComment, RedactComment, AttachFile, RemoveAttachment,
              SwitchPersona, NotFound, Invalid]


@blackbox
def route(req: HttpRequest) -> Route:
    """Turn one HTTP request into a typed view or command. No decisions
    about permission: the kernel makes those when the shell applies it.

    GET routes:
      "/"                 -> ShowQueue(query "q" if it is a QueueKey, else "inbox")
      "/new"              -> ShowNewCase()
      "/case/<id>"        -> ShowCase(id)
    POST routes (fields come from `form`):
      "/case"             -> OpenCase(CaseDraft(subject, org, severity,
                             sla_due)); severity must be high/med/low
                             (default "med"); sla_due is an ISO date or
                             empty (None)
      "/case/<id>/act"    -> MoveCase(id, form "action"); the action must
                             be a CaseAction
      "/case/<id>/edit"   -> EditCase(id, CasePatch(...)); only fields
                             present in the form are set; an empty sla_due
                             means "unchanged"; an empty assignee is kept
                             as "" (it unassigns)
      "/case/<id>/comment"-> PostComment(id, CommentDraft(body,
                             internal = form "internal" == "yes"))
      "/case/<id>/attach" -> AttachFile(id, AttachmentDraft(filename))
      "/comment/<cid>/redact"    with form "case" -> RedactComment(case, cid)
      "/attachment/<aid>/remove" with form "case" -> RemoveAttachment(case, aid)
      "/persona"          -> SwitchPersona(form "persona", "" if absent)
    Ids are positive decimal integers; a path whose id is not one matches
    no route. A malformed FORM field (bad date, unknown severity or action,
    a missing or non-numeric "case" field) yields Invalid(message naming
    the field, back = the page the form came from: ShowCase for
    "/case/<id>/..." forms, ShowNewCase for "/case", ShowQueue("inbox")
    otherwise). Anything else -> NotFound(). Text fields are passed
    through as typed (the kernel trims and validates them)."""
    ...
