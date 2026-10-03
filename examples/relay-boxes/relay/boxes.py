"""REVIEWED — the black-box contracts of Relay.

Everything in this file is reviewed by a human: the types that flow in
and out of black boxes, the capabilities boxes receive, and each box's
signature and description (the docstring — drafted by an LLM, approved
by a human). The bodies are NOT here: each lives in `generated/<name>.py`, is
generated, runs only inside a Monty sandbox, and is held to this file by
type checking (ty, against a stub derived from this file), runtime
conformance checks on every value crossing the boundary, and the tests.

A box cannot write state. It can read the kernel through `DeskReader`
(decided per viewer by machine.py) and return values; the reviewed shell
turns returned commands into kernel calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Protocol, Union

from boxkit import blackbox

from .model import (Actor, Affordance, Attachment, AttachmentDraft, Case,
                    CaseAction, CaseDraft, CasePatch, Comment, CommentDraft,
                    Denied)

# ---------------------------------------------------------------------------
# Capabilities — what a box may call back into

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


Escape = Callable[[str], str]
"""HTML-escapes text for element content AND quoted attribute values."""

OrgDirectory = Callable[[str], Union[str, None]]
"""Maps a sender address to the customer org it belongs to, or None."""

# ---------------------------------------------------------------------------
# Data crossing the UI boundary

QueueKey = Literal["inbox", "working", "waiting", "breached", "resolved", "closed"]


@dataclass(frozen=True)
class Queue:
    key: QueueKey
    label: str
    case_ids: list[int]


QueueSorter = Callable[[list[Case], date], list[Queue]]


@dataclass(frozen=True)
class Notice:
    """A one-line message shown above a page after a request."""
    kind: Literal["ok", "refused", "invalid"]
    text: str
    rule: str | None = None


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

# ---------------------------------------------------------------------------
# The black boxes


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


@blackbox
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    """Partition the cases a viewer can see into the desk's six queues, in
    this order and with these labels: inbox "Inbox" (state new), working
    "Working" (open), waiting "On hold" (waiting), breached "SLA breached",
    resolved "Resolved", closed "Closed". "SLA breached" is a cross-state
    view: every case in new/open/waiting whose sla_due is before `today`
    (such a case is ALSO in its state queue). Within a queue, cases are
    ordered by severity (high, med, low), then by id ascending. Every queue
    is returned, empty or not."""
    ...


@blackbox
def sidebar(current: QueueKey | None, oob: bool, desk: DeskReader,
            sort: QueueSorter, esc: Escape) -> str:
    """The left navigation as one `<aside id="sidebar">` element (add
    `hx-swap-oob="true"` when `oob`). Contents: the "Relay" brand; one link
    per queue from `sort(desk.cases(), desk.today())` with its case count,
    `hx-get="/?q=<key>"` targeting `#content` and pushing the URL, the
    `current` one highlighted and the breached one styled as an alert; a
    "+ New case" button (`hx-get="/new"`); and a persona switcher: a form
    POSTing to "/persona" with a <select name="persona"> listing
    desk.people() as "name (role · org)" plus an "anonymous" option with
    value "", the current viewer (desk.me()) selected, submitting on
    change. Shows the desk date. All text passes through `esc`."""
    ...


@blackbox
def queue_page(queue: QueueKey, notice: Notice | None, desk: DeskReader,
               sort: QueueSorter, esc: Escape) -> str:
    """The main-column HTML for one queue, as `desk.me()` sees it: the
    notice (if any) as a toast — a refusal shows "Refused — rule <rule>"
    with its text; then the queue's label as heading, a count line, and a
    table (severity, subject, org, state, assignee, SLA) of the queue's
    cases in the order `sort` returns them. Each row opens its case
    (`hx-get="/case/<id>"` into `#content`, pushing the URL). SLA cells
    show the due date; for cases in new/open/waiting past due, show it in
    alert style with "N d over". An empty queue says so plainly. All
    user-provided text passes through `esc`."""
    ...


@blackbox
def case_page(case_id: int, notice: Notice | None, desk: DeskReader,
              esc: Escape) -> str:
    """The main-column HTML for one case the viewer can read
    (`desk.case(case_id)` returns a Case; if not, render a short "not
    available" message). Shows: a "← queues" link; the notice toast; the
    subject, state pill, org, SLA; requester, assignee, severity.

    Actions: for each allowed `desk.case_actions(case_id)` a button POSTing
    `{"action": <action>}` to "/case/<id>/act"; refused ones are listed in a
    collapsed "locked" section naming the refusing rule, and are STILL
    clickable (the kernel will refuse them by name — honest affordances).
    If `desk.may_edit` allows: an edit form POSTing subject, assignee,
    severity, sla_due and org to "/case/<id>/edit", and for staff not
    already assigned an "Assign to me" button posting assignee=<me>; else a
    line naming the refusing rule.

    Thread: every comment of `desk.thread(case_id)`, internal ones marked
    "internal"; a redacted one shows a tombstone instead of its body; each
    allowed `desk.comment_actions` action is a small button POSTing to
    "/comment/<cid>/<action>" with form case=<id>. If `desk.may_post(id,
    False)` allows, a form POSTing body to "/case/<id>/comment", with an
    "internal note" checkbox (value "yes") only when `desk.may_post(id,
    True)` also allows; else a line naming the refusing rule.

    Evidence: the same pattern with `desk.evidence`, `attachment_actions`
    ("/attachment/<aid>/<action>"), tombstones for removed files, and an
    attach form (filename) to "/case/<id>/attach" when `desk.may_attach`
    allows. All forms and buttons use htmx (`hx-post`, target `#content`).
    All user-provided text passes through `esc`."""
    ...


@blackbox
def new_case_page(notice: Notice | None, desk: DeskReader, esc: Escape) -> str:
    """The main-column HTML of the "Open a case" form: the notice toast;
    subject; severity select (high/med/low, med preselected); SLA due date;
    org — for a viewer with an org, shown read-only and sent as a hidden
    field, otherwise a text input. POSTs to "/case" with htmx into
    `#content`. All user-provided text passes through `esc`."""
    ...


@blackbox
def document(sidebar_html: str, content_html: str) -> str:
    """The full HTML document: doctype, utf-8, title "Relay — support
    desk", `<script src="/static/htmx.min.js">`, the complete stylesheet
    for every page above (a dark sidebar, light main column, toasts, pills,
    tables, thread and evidence cards, tombstones, locked actions), then
    the sidebar, then `<main id="content">` holding `content_html`
    unchanged. Includes a script that lets htmx swap 403, 404 and 422
    responses (refusals render like any other page)."""
    ...


@blackbox
def intake_email(mail: Email, org_of: OrgDirectory) -> MailIntent:
    """HD-7: interpret one inbound email for the mail robot.

    For every outcome below, "body" means the email body with surrounding
    whitespace trimmed, and "attachments" the attachment names as given,
    dropping empty ones.

    A subject containing "[#<id>]" (anywhere) is a reply to case <id>:
    MailReply(id, body, attachments). Otherwise it opens a case:
    the sender's org is `org_of(mail.sender)` — if None, MailBounce naming
    the unknown sender. The case subject is the email subject with leading
    "Re:"/"Fwd:"/"Fw:" prefixes (any case, repeated) removed and whitespace
    trimmed; if that leaves nothing, MailBounce("empty subject"). Severity
    is "high" if the subject or body contains "urgent" or "outage" (any
    case), else "med"; sla_due is None (staff set it):
    MailNewCase(draft, body, attachments)."""
    ...
