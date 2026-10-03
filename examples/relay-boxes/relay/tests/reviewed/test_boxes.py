"""REVIEWED — what the generated boxes must do, checked through the sandbox.

These tests are the human-owned half of each box's acceptance: they pin
the behaviour the descriptions promise (routing table, queue semantics,
mail interpretation) and the properties no description can be trusted
to deliver alone — escaping of hostile text on every page for every
persona, and every link a page renders being a route the router knows.
Generated tests (tests/generated/) may add to these; they never replace
them.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from relay import boxes as B
from relay.machine import Desk
from relay.model import (AttachmentDraft, Case, CaseDraft, CasePatch,
                         CommentDraft)
from relay.shell import PEOPLE, TODAY, esc, org_of, seed


@pytest.fixture(scope="module")
def desk() -> Desk:
    d = Desk(TODAY, PEOPLE)
    seed(d)
    return d


def req(method: str, path: str, form: dict | None = None, query: dict | None = None):
    return B.route(B.HttpRequest(method, path, query or {}, form or {}))


# ---- route -------------------------------------------------------------------

def test_route_views():
    assert req("GET", "/") == B.ShowQueue("inbox")
    assert req("GET", "/", query={"q": "breached"}) == B.ShowQueue("breached")
    assert req("GET", "/", query={"q": "nonsense"}) == B.ShowQueue("inbox")
    assert req("GET", "/new") == B.ShowNewCase()
    assert req("GET", "/case/12") == B.ShowCase(12)
    assert req("GET", "/case/abc") == B.NotFound()
    assert req("GET", "/etc/passwd") == B.NotFound()


def test_route_commands():
    assert req("POST", "/case", {"subject": "x", "org": "acme", "severity": "high",
                                 "sla_due": "2026-09-01"}) == \
        B.OpenCase(CaseDraft("x", "acme", "high", date(2026, 9, 1)))
    assert req("POST", "/case", {"subject": "x", "org": "acme"}) == \
        B.OpenCase(CaseDraft("x", "acme", "med", None))
    assert req("POST", "/case/3/act", {"action": "triage"}) == B.MoveCase(3, "triage")
    assert req("POST", "/case/3/edit", {"assignee": "sam"}) == \
        B.EditCase(3, CasePatch(assignee="sam"))
    assert req("POST", "/case/3/edit", {"assignee": "", "sla_due": ""}) == \
        B.EditCase(3, CasePatch(assignee=""))
    assert req("POST", "/case/3/comment", {"body": "hi", "internal": "yes"}) == \
        B.PostComment(3, CommentDraft("hi", True))
    assert req("POST", "/case/3/comment", {"body": "hi"}) == \
        B.PostComment(3, CommentDraft("hi", False))
    assert req("POST", "/case/3/attach", {"filename": "a.log"}) == \
        B.AttachFile(3, AttachmentDraft("a.log"))
    assert req("POST", "/comment/7/redact", {"case": "3"}) == B.RedactComment(3, 7)
    assert req("POST", "/attachment/9/remove", {"case": "3"}) == B.RemoveAttachment(3, 9)
    assert req("POST", "/persona", {"persona": "noor"}) == B.SwitchPersona("noor")


def test_route_rejects_malformed_fields_by_name():
    bad = req("POST", "/case", {"subject": "x", "org": "a", "sla_due": "tomorrow"})
    assert isinstance(bad, B.Invalid) and "sla_due" in bad.message
    assert bad.back == B.ShowNewCase()
    bad = req("POST", "/case/3/act", {"action": "delete"})
    assert isinstance(bad, B.Invalid) and bad.back == B.ShowCase(3)
    bad = req("POST", "/case", {"subject": "x", "org": "a", "severity": "apocalyptic"})
    assert isinstance(bad, B.Invalid) and "severity" in bad.message
    assert isinstance(req("POST", "/comment/7/redact", {}), B.Invalid)


# ---- sort_into_queues -----------------------------------------------------------

def mk(i, state, sev="med", due=None):
    return Case(i, f"c{i}", "acme", "dana", state, sev, None, due)


def test_queues_order_labels_and_cross_state_breach():
    past, future = date(2026, 8, 1), date(2026, 9, 1)
    cases = [mk(1, "new", "low", past), mk(2, "new", "high"), mk(3, "open", "med", past),
             mk(4, "waiting", "high", past), mk(5, "resolved", "high", past),
             mk(6, "closed", "low", past), mk(7, "new", "high", future)]
    qs = B.sort_into_queues(cases, TODAY)
    assert [(q.key, q.label) for q in qs] == [
        ("inbox", "Inbox"), ("working", "Working"), ("waiting", "On hold"),
        ("breached", "SLA breached"), ("resolved", "Resolved"), ("closed", "Closed")]
    got = {q.key: q.case_ids for q in qs}
    assert got["inbox"] == [2, 7, 1]            # high before low, then id
    assert got["breached"] == [4, 3, 1]         # resolved/closed never breach
    assert got["resolved"] == [5] and got["closed"] == [6]
    assert B.sort_into_queues([], TODAY)[0].case_ids == []


def test_due_today_is_not_breached():
    qs = B.sort_into_queues([mk(1, "open", due=TODAY)], TODAY)
    assert {q.key: q.case_ids for q in qs}["breached"] == []


# ---- intake_email -----------------------------------------------------------------

def test_mail_reply_new_case_and_bounces():
    m = B.intake_email(B.Email("x@acme.example", "RE: [#12] still broken", "  more  ", ["a.png", ""]), org_of)
    assert m == B.MailReply(12, "more", ["a.png"])
    m = B.intake_email(B.Email("dana@acme.example", "Fwd: re: FW: Outage in EU", "help", []), org_of)
    assert m == B.MailNewCase(CaseDraft("Outage in EU", "acme", "high", None), "help", [])
    m = B.intake_email(B.Email("dana@acme.example", "Question", "is this URGENT?", []), org_of)
    assert isinstance(m, B.MailNewCase) and m.draft.severity == "high"
    m = B.intake_email(B.Email("dana@acme.example", "Question", "when?", []), org_of)
    assert isinstance(m, B.MailNewCase) and m.draft.severity == "med"
    assert isinstance(B.intake_email(B.Email("eve@evil.example", "hi", "", []), org_of), B.MailBounce)
    assert B.intake_email(B.Email("dana@acme.example", "Re: ", "x", []), org_of) == \
        B.MailBounce("empty subject")


# ---- pages: escaping, affordances, link consistency ------------------------------------

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


def every_page(d: Desk, who: str) -> dict[str, str]:
    v = d.view(d.actor(who))
    pages = {"sidebar": B.sidebar("inbox", False, v, B.sort_into_queues, esc),
             "new": B.new_case_page(B.Notice("refused", HOSTILE, "org_walls"), v, esc)}
    for q in ("inbox", "working", "breached"):
        pages[f"queue:{q}"] = B.queue_page(q, B.Notice("invalid", HOSTILE), v, B.sort_into_queues, esc)
    for c in v.cases():
        pages[f"case:{c.id}"] = B.case_page(c.id, B.Notice("ok", HOSTILE), v, esc)
    return pages


@pytest.mark.parametrize("who", ["dana", "sam", "noor", "omar", "anonymous"])
def test_no_page_ever_renders_hostile_text_unescaped(hostile_desk, who):
    for name, html in every_page(hostile_desk, who).items():
        assert "<script>alert" not in html, (who, name)
        assert "<img src=x" not in html, (who, name)
        assert '"><img' not in html, (who, name)


def test_internal_notes_never_reach_customer_pages(desk):
    for who in ("dana", "priya"):
        for name, html in every_page(desk, who).items():
            assert "SAML clock skew" not in html and "template v2" not in html, (who, name)
    staff = every_page(desk, "sam")
    assert any("SAML clock skew" in h for h in staff.values())


def test_refusals_are_shown_by_rule_name(desk):
    v = desk.view(desk.actor("dana"))
    closed = next(c for c in v.cases() if c.state == "closed")
    page = B.case_page(closed.id, None, v, esc)
    assert "sealed_after_resolution" in page and "sealed_thread" in page
    assert f'hx-post="/case/{closed.id}/comment"' not in page
    sam = desk.view(desk.actor("quinn"))
    mine_not = next(c for c in sam.cases() if c.state == "open" and c.assignee == "sam")
    assert "only_assignee_resolves" in B.case_page(mine_not.id, None, sam, esc)


def test_internal_checkbox_only_for_staff(desk):
    case_id = next(c.id for c in desk.view(desk.actor("dana")).cases() if c.state == "open")
    assert 'name="internal"' in B.case_page(case_id, None, desk.view(desk.actor("sam")), esc)
    assert 'name="internal"' not in B.case_page(case_id, None, desk.view(desk.actor("dana")), esc)


def test_every_rendered_link_and_form_is_a_route_the_router_knows(desk):
    for who in ("dana", "sam", "noor"):
        for name, html in every_page(desk, who).items():
            for verb, url in re.findall(r'hx-(get|post)="([^"]+)"', html):
                path, _, qs = url.partition("?")
                query = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                got = req(verb.upper(), path, {"case": "1", "action": "triage"}, query)
                assert not isinstance(got, B.NotFound), (who, name, verb, url)


def test_document_wraps_content_verbatim():
    doc = B.document('<aside id="sidebar">S</aside>', "<p>CONTENT&amp;</p>")
    assert doc.lower().startswith("<!doctype html>")
    assert '<main id="content"><p>CONTENT&amp;</p></main>' in doc
    assert '<aside id="sidebar">S</aside>' in doc
    assert 'src="/static/htmx.min.js"' in doc


def test_sidebar_out_of_band_flag_and_persona_switcher(desk):
    v = desk.view(desk.actor("dana"))
    oob = B.sidebar(None, True, v, B.sort_into_queues, esc)
    assert 'id="sidebar"' in oob and 'hx-swap-oob="true"' in oob
    plain = B.sidebar("inbox", False, v, B.sort_into_queues, esc)
    assert 'hx-swap-oob' not in plain
    assert 'action="/persona"' in plain and 'name="persona"' in plain
    for p in PEOPLE:
        assert f'value="{p.name}"' in plain
