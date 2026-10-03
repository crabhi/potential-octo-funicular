"""REVIEWED — the page frame shared by every page: contracts only, bodies
in generated.relay.web.ui."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from boxkit import blackbox
from relay.cases.queues import QueueKey, QueueSorter
from relay.kernel import DeskReader

Escape = Callable[[str], str]
"""HTML-escapes text for element content AND quoted attribute values."""


@dataclass(frozen=True)
class Notice:
    """A one-line message shown above a page after a request."""
    kind: Literal["ok", "refused", "invalid"]
    text: str
    rule: str | None = None


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
def document(sidebar_html: str, content_html: str) -> str:
    """The full HTML document: doctype, utf-8, title "Relay — support
    desk", `<script src="/static/htmx.min.js">`, the complete stylesheet
    for every page above (a dark sidebar, light main column, toasts, pills,
    tables, thread and evidence cards, tombstones, locked actions), then
    the sidebar, then `<main id="content">` holding `content_html`
    unchanged. Includes a script that lets htmx swap 403, 404 and 422
    responses (refusals render like any other page)."""
    ...
