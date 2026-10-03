"""REVIEWED — the case pages (relay.cases.pages) as every persona sees them:
hostile text is always escaped, internal notes never reach customers,
refusals are shown by rule name, and every link is a route the router knows."""

from __future__ import annotations

import re

import pytest

from relay.cases.pages import case_page
from relay.web.routes import HttpRequest, NotFound, route
from relay.web.server import esc


def req(method: str, path: str, form: dict | None = None, query: dict | None = None):
    return route(HttpRequest(method, path, query or {}, form or {}))


@pytest.mark.parametrize("who", ["dana", "sam", "noor", "omar", "anonymous"])
def test_no_page_ever_renders_hostile_text_unescaped(hostile_desk, who, pages):
    for name, html in pages(hostile_desk, who).items():
        assert "<script>alert" not in html, (who, name)
        assert "<img src=x" not in html, (who, name)
        assert '"><img' not in html, (who, name)


def test_internal_notes_never_reach_customer_pages(desk, pages):
    for who in ("dana", "priya"):
        for name, html in pages(desk, who).items():
            assert "SAML clock skew" not in html and "template v2" not in html, (who, name)
    staff = pages(desk, "sam")
    assert any("SAML clock skew" in h for h in staff.values())


def test_refusals_are_shown_by_rule_name(desk):
    v = desk.view(desk.actor("dana"))
    closed = next(c for c in v.cases() if c.state == "closed")
    page = case_page(closed.id, None, v, esc)
    assert "sealed_after_resolution" in page and "sealed_thread" in page
    assert f'hx-post="/case/{closed.id}/comment"' not in page
    sam = desk.view(desk.actor("quinn"))
    mine_not = next(c for c in sam.cases() if c.state == "open" and c.assignee == "sam")
    assert "only_assignee_resolves" in case_page(mine_not.id, None, sam, esc)


def test_internal_checkbox_only_for_staff(desk):
    case_id = next(c.id for c in desk.view(desk.actor("dana")).cases() if c.state == "open")
    assert 'name="internal"' in case_page(case_id, None, desk.view(desk.actor("sam")), esc)
    assert 'name="internal"' not in case_page(case_id, None, desk.view(desk.actor("dana")), esc)


def test_every_rendered_link_and_form_is_a_route_the_router_knows(desk, pages):
    for who in ("dana", "sam", "noor"):
        for name, html in pages(desk, who).items():
            for verb, url in re.findall(r'hx-(get|post)="([^"]+)"', html):
                path, _, qs = url.partition("?")
                query = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                got = req(verb.upper(), path, {"case": "1", "action": "triage"}, query)
                assert not isinstance(got, NotFound), (who, name, verb, url)
