"""Generated, additive tests pinning the `route` description."""
from __future__ import annotations

from datetime import date

import pytest

import relay.boxes as B

QUEUES = ["inbox", "working", "waiting", "breached", "resolved", "closed"]
ACTIONS = ["triage", "wait", "reply", "resolve", "reopen", "close"]


def get(path, **query):
    return B.route(B.HttpRequest("GET", path, dict(query), {}))


def post(path, **form):
    return B.route(B.HttpRequest("POST", path, {}, dict(form)))


# ---------------------------------------------------------------- GET routes

@pytest.mark.parametrize("q", QUEUES)
def test_root_shows_each_queue_key(q):
    assert get("/", q=q) == B.ShowQueue(q)


@pytest.mark.parametrize("query", [{}, {"q": ""}, {"q": "bogus"}, {"q": "Working"}, {"q": "inbox "}, {"x": "working"}])
def test_root_defaults_to_inbox(query):
    assert B.route(B.HttpRequest("GET", "/", query, {})) == B.ShowQueue("inbox")


def test_root_ignores_form_on_get():
    assert B.route(B.HttpRequest("GET", "/", {"q": "closed"}, {"q": "working"})) == B.ShowQueue("closed")


def test_new_case_form():
    assert get("/new") == B.ShowNewCase()


@pytest.mark.parametrize("cid", [1, 7, 42, 1234567890123])
def test_show_case(cid):
    assert get(f"/case/{cid}") == B.ShowCase(cid)


@pytest.mark.parametrize("path", ["/case/0", "/case/-1", "/case/abc", "/case/1x", "/case/1.5", "/case/", "/case"])
def test_get_case_with_bad_id_is_not_found(path):
    assert get(path) == B.NotFound()


@pytest.mark.parametrize("path", ["/nope", "/new/extra", "/case/1/act", "/case/1/edit", "/persona", "/case/1/comment"])
def test_unknown_get_paths_are_not_found(path):
    assert get(path) == B.NotFound()


# --------------------------------------------------------------- POST /case

def test_open_case_full():
    r = post("/case", subject="Printer on fire", org="acme", severity="high", sla_due="2026-09-01")
    assert r == B.OpenCase(B.CaseDraft("Printer on fire", "acme", "high", date(2026, 9, 1)))


@pytest.mark.parametrize("sev", ["high", "med", "low"])
def test_open_case_severities(sev):
    r = post("/case", subject="s", org="o", severity=sev)
    assert isinstance(r, B.OpenCase) and r.draft.severity == sev


def test_open_case_severity_defaults_to_med():
    r = post("/case", subject="s", org="o", sla_due="")
    assert r == B.OpenCase(B.CaseDraft("s", "o", "med", None))


def test_open_case_empty_sla_is_none():
    r = post("/case", subject="s", org="o", severity="low", sla_due="")
    assert r.draft.sla_due is None


def test_open_case_text_fields_passed_through_untrimmed():
    r = post("/case", subject="  Hello  ", org=" acme ", severity="med")
    assert r.draft.subject == "  Hello  "
    assert r.draft.org == " acme "


@pytest.mark.parametrize("sev", ["urgent", "HIGH", "critical", "2"])
def test_open_case_unknown_severity_is_invalid_back_to_new_case(sev):
    r = post("/case", subject="s", org="o", severity=sev)
    assert isinstance(r, B.Invalid)
    assert "severity" in r.message
    assert r.back == B.ShowNewCase()


@pytest.mark.parametrize("bad", ["tomorrow", "2026-13-01", "2026-02-30", "01/02/2026", "2026-9"])
def test_open_case_bad_date_is_invalid_back_to_new_case(bad):
    r = post("/case", subject="s", org="o", severity="med", sla_due=bad)
    assert isinstance(r, B.Invalid)
    assert "sla_due" in r.message
    assert r.back == B.ShowNewCase()


# ----------------------------------------------------------- POST /case/<id>/act

@pytest.mark.parametrize("action", ACTIONS)
def test_act_each_action(action):
    assert post("/case/5/act", action=action) == B.MoveCase(5, action)


@pytest.mark.parametrize("action", ["explode", "Resolve", "", "delete"])
def test_act_unknown_action_is_invalid_back_to_case(action):
    r = post("/case/5/act", action=action)
    assert isinstance(r, B.Invalid)
    assert "action" in r.message
    assert r.back == B.ShowCase(5)


# ---------------------------------------------------------- POST /case/<id>/edit

def test_edit_all_fields():
    r = post("/case/3/edit", subject="New subj", org="zephyr", severity="low",
             assignee="quinn", sla_due="2026-10-01")
    assert r == B.EditCase(3, B.CasePatch("New subj", "zephyr", "low", "quinn", date(2026, 10, 1)))


def test_edit_only_present_fields_are_set():
    assert post("/case/3/edit", severity="high") == B.EditCase(3, B.CasePatch(severity="high"))
    assert post("/case/3/edit", subject="Only") == B.EditCase(3, B.CasePatch(subject="Only"))
    assert post("/case/3/edit", org="zephyr") == B.EditCase(3, B.CasePatch(org="zephyr"))


def test_edit_with_no_fields_changes_nothing():
    assert post("/case/3/edit") == B.EditCase(3, B.CasePatch())


def test_edit_empty_sla_means_unchanged():
    r = post("/case/3/edit", sla_due="", severity="low")
    assert r == B.EditCase(3, B.CasePatch(severity="low"))
    assert r.patch.sla_due is None


def test_edit_empty_assignee_is_kept_as_empty_string():
    r = post("/case/3/edit", assignee="")
    assert r == B.EditCase(3, B.CasePatch(assignee=""))
    assert r.patch.assignee == ""


def test_edit_bad_severity_is_invalid_back_to_case():
    r = post("/case/3/edit", severity="huge")
    assert isinstance(r, B.Invalid) and "severity" in r.message
    assert r.back == B.ShowCase(3)


def test_edit_bad_date_is_invalid_back_to_case():
    r = post("/case/3/edit", sla_due="soon")
    assert isinstance(r, B.Invalid) and "sla_due" in r.message
    assert r.back == B.ShowCase(3)


# ------------------------------------------------------- POST /case/<id>/comment

def test_comment_public_by_default():
    assert post("/case/9/comment", body="hello") == B.PostComment(9, B.CommentDraft("hello", False))


def test_comment_internal_only_when_yes():
    assert post("/case/9/comment", body="b", internal="yes") == B.PostComment(9, B.CommentDraft("b", True))
    for other in ["no", "on", "true", "YES", "", "1"]:
        r = post("/case/9/comment", body="b", internal=other)
        assert r == B.PostComment(9, B.CommentDraft("b", False)), other


def test_comment_body_passed_through_as_typed():
    r = post("/case/9/comment", body="  spaced\n text  ")
    assert r.draft.body == "  spaced\n text  "


# --------------------------------------------------------- POST /case/<id>/attach

def test_attach_file():
    assert post("/case/2/attach", filename="shot.png") == B.AttachFile(2, B.AttachmentDraft("shot.png"))


# ------------------------------------------------------------ redact / remove

def test_redact_comment():
    assert post("/comment/12/redact", case="3") == B.RedactComment(3, 12)


def test_remove_attachment():
    assert post("/attachment/8/remove", case="4") == B.RemoveAttachment(4, 8)


@pytest.mark.parametrize("form", [{}, {"case": "abc"}, {"case": ""}, {"case": "1.5"}])
def test_redact_bad_case_field_is_invalid_back_to_inbox(form):
    r = post("/comment/12/redact", **form)
    assert isinstance(r, B.Invalid)
    assert "case" in r.message
    assert r.back == B.ShowQueue("inbox")


@pytest.mark.parametrize("form", [{}, {"case": "x"}])
def test_remove_bad_case_field_is_invalid_back_to_inbox(form):
    r = post("/attachment/8/remove", **form)
    assert isinstance(r, B.Invalid)
    assert "case" in r.message
    assert r.back == B.ShowQueue("inbox")


@pytest.mark.parametrize("path", ["/comment/x/redact", "/comment/0/redact", "/comment/-3/redact",
                                  "/attachment/y/remove", "/attachment/0/remove",
                                  "/comment/1/delete", "/attachment/1/redact"])
def test_redact_remove_bad_path_is_not_found(path):
    assert post(path, case="1") == B.NotFound()


# -------------------------------------------------------------------- persona

def test_switch_persona():
    assert post("/persona", persona="dana") == B.SwitchPersona("dana")


def test_switch_persona_absent_is_empty_string():
    assert post("/persona") == B.SwitchPersona("")
    assert post("/persona", persona="") == B.SwitchPersona("")


# ---------------------------------------------------------------- not found

@pytest.mark.parametrize("path", ["/case/0/act", "/case/-2/act", "/case/abc/act", "/case/1x/edit",
                                  "/case/x/comment", "/case/0/attach"])
def test_post_with_bad_id_is_not_found_not_invalid(path):
    assert post(path, action="close", body="b", filename="f") == B.NotFound()


@pytest.mark.parametrize("path", ["/", "/new", "/nope", "/case/1", "/case/1/unknown", "/case/1/act/extra"])
def test_unknown_post_paths_are_not_found(path):
    assert post(path, action="close") == B.NotFound()


@pytest.mark.parametrize("path", ["/case/1/act", "/case/1/edit", "/case/1/comment", "/case/1/attach",
                                  "/persona", "/case/1/foo"])
def test_get_on_post_only_routes_is_not_found(path):
    assert get(path) == B.NotFound()


def test_post_to_get_only_routes_is_not_found():
    assert post("/new") == B.NotFound()
    assert post("/case/1") == B.NotFound()
