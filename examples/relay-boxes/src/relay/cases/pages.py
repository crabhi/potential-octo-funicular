"""REVIEWED — the pages of the case desk: contracts only. The HTML is
generated (generated.relay.cases.pages), reads the kernel through the
viewer's DeskReader, and never decides anything."""

from __future__ import annotations

from boxkit import blackbox
from relay.cases.queues import QueueKey, QueueSorter
from relay.kernel import DeskReader
from relay.web.ui import Escape, Notice


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
