"""REVIEWED — shared fixtures: a seeded desk, a desk full of hostile text,
and helpers to call the router and render every page as a persona."""

from __future__ import annotations

from datetime import date

import pytest

from relay.cases.model import CaseDraft, CasePatch
from relay.cases.pages import case_page, new_case_page, queue_page
from relay.cases.queues import sort_into_queues
from relay.kernel import Desk
from relay.thread.model import AttachmentDraft, CommentDraft
from relay.web.routes import HttpRequest, route
from relay.web.seed import PEOPLE, TODAY, seed
from relay.web.server import esc
from relay.web.ui import Notice, sidebar


@pytest.fixture(scope="module")
def desk() -> Desk:
    d = Desk(TODAY, PEOPLE)
    seed(d)
    return d


HOSTILE = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


@pytest.fixture(scope="module")
def hostile_desk() -> Desk:
    d = Desk(TODAY, PEOPLE)
    dana, sam = d.actor("dana"), d.actor("sam")
    c = d.open_case(dana, CaseDraft(HOSTILE, "acme", "high", date(2026, 8, 1)))
    d.post_comment(dana, c.id, CommentDraft(HOSTILE, False))
    d.attach(dana, c.id, AttachmentDraft(HOSTILE))
    d.edit_case(sam, c.id, CasePatch(assignee=HOSTILE))
    d.open_case(sam, CaseDraft("staff-opened", HOSTILE, "low", None))
    return d


def req(method: str, path: str, form: dict | None = None, query: dict | None = None):
    return route(HttpRequest(method, path, query or {}, form or {}))


def every_page(d: Desk, who: str) -> dict[str, str]:
    v = d.view(d.actor(who))
    pages = {"sidebar": sidebar("inbox", False, v, sort_into_queues, esc),
             "new": new_case_page(Notice("refused", HOSTILE, "org_walls"), v, esc)}
    for q in ("inbox", "working", "breached"):
        pages[f"queue:{q}"] = queue_page(q, Notice("invalid", HOSTILE), v, sort_into_queues, esc)
    for c in v.cases():
        pages[f"case:{c.id}"] = case_page(c.id, Notice("ok", HOSTILE), v, esc)
    return pages


@pytest.fixture()
def pages():
    """every_page(desk, persona) -> {page name: html}"""
    return every_page
