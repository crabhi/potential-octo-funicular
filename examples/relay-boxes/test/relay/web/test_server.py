"""REVIEWED — the whole app over real HTTP: generated UI, reviewed kernel.

Forged requests (buttons the UI never rendered, hidden fields flipped,
other orgs' ids) must bounce off the kernel with the refusing rule named
in the response — whatever the generated pages chose to show.
"""

from __future__ import annotations

import http.client
import threading
import urllib.parse

import pytest

from relay.mail.gateway import MAIL_TOKEN
from relay.web.seed import seed
from relay.web.server import build


@pytest.fixture(scope="module")
def server():
    desk, httpd = build(0)
    seed(desk)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield desk, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def call(server, method, path, who="", form=None, headers=None):
    _, port = server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    body = urllib.parse.urlencode(form or {})
    h = {"Cookie": f"persona={who}", "Content-Type": "application/x-www-form-urlencoded",
         **(headers or {})}
    conn.request(method, path, body=body if method == "POST" else None, headers=h)
    r = conn.getresponse()
    return r.status, r.read().decode(), dict(r.getheaders())


def case_id(server, subject):
    desk, _ = server
    noor = desk.actor("noor")
    return next(c.id for c in desk.visible_cases(noor) if c.subject == subject)


def test_every_persona_gets_a_full_page(server):
    for who in ("dana", "omar", "sam", "noor", "postbot", ""):
        status, body, _ = call(server, "GET", "/", who)
        assert status == 200 and '<main id="content">' in body, who


def test_queues_are_the_read_rule(server):
    _, dana, _ = call(server, "GET", "/?q=working", "dana")
    _, omar, _ = call(server, "GET", "/?q=working", "omar")
    assert "Login broken" in dana and "Login broken" not in omar
    assert "API 500s" in omar and "API 500s" not in dana


def test_forged_requests_bounce_by_rule_name(server):
    sso = case_id(server, "Login broken for SSO users")
    zephyr = case_id(server, "API 500s on bulk upload")
    cases = [
        ("dana", f"/case/{zephyr}", "GET", {}, "org_walls"),
        ("dana", f"/case/{zephyr}/act", "POST", {"action": "triage"}, "org_walls"),
        ("dana", f"/case/{sso}/act", "POST", {"action": "resolve"}, "default_deny"),
        ("dana", f"/case/{sso}/comment", "POST", {"body": "x", "internal": "yes"},
         "internal_is_staff_only"),
        ("quinn", f"/case/{sso}/act", "POST", {"action": "resolve"}, "only_assignee_resolves"),
        ("dana", f"/case/{sso}/edit", "POST", {"org": "zephyr"}, "org_walls"),
    ]
    for who, path, method, form, rule in cases:
        status, body, _ = call(server, method, path, who, form)
        assert status == 403 and rule in body, (who, path, status)


def test_robot_cannot_redact_or_read(server):
    desk, _ = server
    sso = case_id(server, "Login broken for SSO users")
    cid = desk.thread(desk.actor("noor"), sso)[0].id
    status, body, _ = call(server, "POST", f"/comment/{cid}/redact", "postbot", {"case": str(sso)})
    assert status == 403
    status, body, _ = call(server, "GET", f"/case/{sso}", "postbot")
    assert status == 403 and "default_deny" in body


def test_a_real_flow_and_htmx_partials(server):
    status, body, _ = call(server, "POST", "/case", "priya",
                           {"subject": "Dark mode flickers", "org": "acme", "severity": "low"},
                           {"HX-Request": "true"})
    assert status == 200 and "Dark mode flickers" in body
    assert 'hx-swap-oob="true"' in body and "<!doctype" not in body.lower()
    new = case_id(server, "Dark mode flickers")
    assert call(server, "POST", f"/case/{new}/act", "sam", {"action": "triage"})[0] == 200
    assert call(server, "POST", f"/case/{new}/edit", "sam", {"assignee": "sam"})[0] == 200
    assert call(server, "POST", f"/case/{new}/act", "sam", {"action": "resolve"})[0] == 200
    status, body, _ = call(server, "POST", f"/case/{new}/attach", "priya", {"filename": "late.png"})
    assert status == 403 and "fresh_evidence_only" in body


def test_invalid_input_is_422_and_unknown_is_404(server):
    status, body, _ = call(server, "POST", "/case", "dana",
                           {"subject": "x", "org": "acme", "sla_due": "someday"})
    assert status == 422 and "sla_due" in body
    assert call(server, "GET", "/wp-admin", "dana")[0] == 404


def test_persona_switch_sets_cookie(server):
    status, _, headers = call(server, "POST", "/persona", "", {"persona": "noor"})
    assert status == 303 and "persona=noor" in headers["Set-Cookie"]


def test_mail_gateway_needs_its_token_and_checks_the_sender(server):
    form = {"sender": "omar@zephyr.example", "subject": "Webhooks down",
            "body": "since noon", "attachments": "log.txt"}
    assert call(server, "POST", "/inbound-mail", "", form)[0] == 401
    tok = {"X-Relay-Mail-Token": MAIL_TOKEN}
    status, body, _ = call(server, "POST", "/inbound-mail", "", form, tok)
    assert status == 200 and body.startswith("filed on case #")
    sso = case_id(server, "Login broken for SSO users")  # an acme case
    forged = {"sender": "omar@zephyr.example", "subject": f"Re: [#{sso}] hi", "body": "x"}
    status, body, _ = call(server, "POST", "/inbound-mail", "", forged, tok)
    assert body.startswith("bounced")
