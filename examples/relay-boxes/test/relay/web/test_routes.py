"""REVIEWED — `route` (relay.web.routes): the routing table its description
promises, and malformed fields refused by name."""

from __future__ import annotations

from datetime import date

from relay.cases.model import CaseDraft, CasePatch
from relay.thread.model import AttachmentDraft, CommentDraft
from relay.web.routes import (
    AttachFile,
    EditCase,
    HttpRequest,
    Invalid,
    MoveCase,
    NotFound,
    OpenCase,
    PostComment,
    RedactComment,
    RemoveAttachment,
    ShowCase,
    ShowNewCase,
    ShowQueue,
    SwitchPersona,
    route,
)


def req(method: str, path: str, form: dict | None = None, query: dict | None = None):
    return route(HttpRequest(method, path, query or {}, form or {}))


def test_route_views():
    assert req("GET", "/") == ShowQueue("inbox")
    assert req("GET", "/", query={"q": "breached"}) == ShowQueue("breached")
    assert req("GET", "/", query={"q": "nonsense"}) == ShowQueue("inbox")
    assert req("GET", "/new") == ShowNewCase()
    assert req("GET", "/case/12") == ShowCase(12)
    assert req("GET", "/case/abc") == NotFound()
    assert req("GET", "/etc/passwd") == NotFound()


def test_route_commands():
    assert req("POST", "/case", {"subject": "x", "org": "acme", "severity": "high",
                                 "sla_due": "2026-09-01"}) == \
        OpenCase(CaseDraft("x", "acme", "high", date(2026, 9, 1)))
    assert req("POST", "/case", {"subject": "x", "org": "acme"}) == \
        OpenCase(CaseDraft("x", "acme", "med", None))
    assert req("POST", "/case/3/act", {"action": "triage"}) == MoveCase(3, "triage")
    assert req("POST", "/case/3/edit", {"assignee": "sam"}) == \
        EditCase(3, CasePatch(assignee="sam"))
    assert req("POST", "/case/3/edit", {"assignee": "", "sla_due": ""}) == \
        EditCase(3, CasePatch(assignee=""))
    assert req("POST", "/case/3/comment", {"body": "hi", "internal": "yes"}) == \
        PostComment(3, CommentDraft("hi", True))
    assert req("POST", "/case/3/comment", {"body": "hi"}) == \
        PostComment(3, CommentDraft("hi", False))
    assert req("POST", "/case/3/attach", {"filename": "a.log"}) == \
        AttachFile(3, AttachmentDraft("a.log"))
    assert req("POST", "/comment/7/redact", {"case": "3"}) == RedactComment(3, 7)
    assert req("POST", "/attachment/9/remove", {"case": "3"}) == RemoveAttachment(3, 9)
    assert req("POST", "/persona", {"persona": "noor"}) == SwitchPersona("noor")


def test_route_rejects_malformed_fields_by_name():
    bad = req("POST", "/case", {"subject": "x", "org": "a", "sla_due": "tomorrow"})
    assert isinstance(bad, Invalid) and "sla_due" in bad.message
    assert bad.back == ShowNewCase()
    bad = req("POST", "/case/3/act", {"action": "delete"})
    assert isinstance(bad, Invalid) and bad.back == ShowCase(3)
    bad = req("POST", "/case", {"subject": "x", "org": "a", "severity": "apocalyptic"})
    assert isinstance(bad, Invalid) and "severity" in bad.message
    assert isinstance(req("POST", "/comment/7/redact", {}), Invalid)
