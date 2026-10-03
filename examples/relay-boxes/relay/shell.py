"""REVIEWED — the outer code: HTTP plumbing, side effects, wiring.

    python -m relay.shell               # serve on :8811 with a seeded desk
    python -m relay.shell --port 0      # ephemeral port
    python -m relay.shell --seed-only   # boot, seed, print summary, exit

This is the only place where black-box outputs become effects. A request
flows: `route` (box) parses it into a typed view/command → `apply` (here)
turns a command into ONE kernel call as the cookie's persona → the page
boxes render the result, reading the kernel through the persona's
read-only `DeskReader`. Inbound mail flows the same way: `intake_email`
(box) interprets, `receive_mail` (here) applies as the robot.

No HTML is written here and no product decision is made here: what the
desk looks like is generated (impl/), who may do what is machine.py.
"""

from __future__ import annotations

import argparse
import hmac
import html
import os
import pathlib
import sys
import urllib.parse
from datetime import date
from http import cookies as cookies_mod
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boxkit import BoxError, ContractViolation

from . import boxes as B
from .machine import Desk
from .model import (Actor, AttachmentDraft, Case, CaseDraft, CasePatch,
                    CommentDraft, Denied)

HERE = pathlib.Path(__file__).resolve().parent
STATIC = HERE.parent / "static"
TODAY = date(2026, 8, 14)

PEOPLE = [
    Actor("dana", "customer", "acme"),
    Actor("priya", "customer", "acme"),
    Actor("lex", "customer", "acme", active=False),
    Actor("omar", "customer", "zephyr"),
    Actor("sam", "agent"),
    Actor("quinn", "agent"),
    Actor("noor", "lead"),
    Actor("postbot", "mailbot"),
]
ORG_DOMAINS = {"acme.example": "acme", "zephyr.example": "zephyr"}
MAIL_TOKEN = os.environ.get("RELAY_MAIL_TOKEN", "dev-mail-token")


# -- capabilities handed to boxes ---------------------------------------------

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def org_of(address: str) -> str | None:
    return ORG_DOMAINS.get(address.rsplit("@", 1)[-1].strip().lower().rstrip(">"))


# -- commands → kernel ----------------------------------------------------------

View = B.ShowQueue | B.ShowCase | B.ShowNewCase


def refused(d: Denied) -> B.Notice:
    return B.Notice("refused", d.reason, d.rule)


def apply(desk: Desk, actor: Actor, cmd: B.Route) -> tuple[View, B.Notice | None, int]:
    """One typed command → one kernel call. Returns the page to show next,
    the notice for it, and the HTTP status."""
    if isinstance(cmd, (B.ShowQueue, B.ShowCase, B.ShowNewCase)):
        return cmd, None, 200
    if isinstance(cmd, B.Invalid):
        return cmd.back, B.Notice("invalid", cmd.message), 422
    if isinstance(cmd, B.OpenCase):
        got = desk.open_case(actor, cmd.draft)
        if isinstance(got, Denied):
            return B.ShowNewCase(), refused(got), 403
        return B.ShowCase(got.id), B.Notice("ok", f"Case #{got.id} opened."), 200

    if isinstance(cmd, B.EditCase):
        case_id, got, ok = cmd.case_id, desk.edit_case(actor, cmd.case_id, cmd.patch), "Changes saved."
    elif isinstance(cmd, B.MoveCase):
        case_id, got, ok = cmd.case_id, desk.move_case(actor, cmd.case_id, cmd.action), f"{cmd.action} — done."
    elif isinstance(cmd, B.PostComment):
        case_id, got, ok = cmd.case_id, desk.post_comment(actor, cmd.case_id, cmd.draft), "Posted to the thread."
    elif isinstance(cmd, B.AttachFile):
        case_id, got, ok = cmd.case_id, desk.attach(actor, cmd.case_id, cmd.draft), "Evidence attached."
    elif isinstance(cmd, B.RedactComment):
        case_id, got, ok = cmd.case_id, desk.act_on_comment(actor, cmd.comment_id, "redact"), "Comment redacted."
    elif isinstance(cmd, B.RemoveAttachment):
        case_id, got, ok = cmd.case_id, desk.act_on_attachment(actor, cmd.attachment_id, "remove"), "Attachment removed."
    else:  # NotFound, or SwitchPersona reaching here by mistake
        return B.ShowQueue("inbox"), None, 404

    if got is None:
        return B.ShowQueue("inbox"), None, 404
    if isinstance(got, Denied):
        return B.ShowCase(case_id), refused(got), 403
    return B.ShowCase(case_id), B.Notice("ok", ok), 200


def render(desk: Desk, actor: Actor, view: View, notice: B.Notice | None,
           status: int) -> tuple[str, int]:
    """Main-column HTML for a view, as `actor` sees it."""
    reader = desk.view(actor)
    if isinstance(view, B.ShowCase):
        got = desk.get_case(actor, view.case_id)
        if isinstance(got, Case):
            return B.case_page(view.case_id, notice, reader, esc), status
        notice = refused(got) if isinstance(got, Denied) else notice
        view, status = B.ShowQueue("inbox"), (403 if isinstance(got, Denied) else 404)
    if isinstance(view, B.ShowNewCase):
        return B.new_case_page(notice, reader, esc), status
    return B.queue_page(view.queue, notice, reader, B.sort_into_queues, esc), status


# -- the mail gateway (HD-7) -----------------------------------------------------

def receive_mail(desk: Desk, mail: B.Email) -> str:
    """Interpret one email (box), then act on it as the robot (here)."""
    robot = desk.actor("postbot")
    intent = B.intake_email(mail, org_of)
    if isinstance(intent, B.MailBounce):
        return f"bounced: {intent.reason}"
    if isinstance(intent, B.MailNewCase):
        got = desk.open_case(robot, intent.draft)
        if isinstance(got, Denied):
            return f"refused: {got.rule}"
        case_id = got.id
        if intent.body:
            desk.post_comment(robot, case_id, CommentDraft(intent.body, False))
    else:
        case_id = intent.case_id
        case_org = desk.org_of_case(case_id)
        # a reply may only land on a case of the sender's own org — the
        # robot cannot read the case, so the gateway checks for it
        if case_org is None or org_of(mail.sender) != case_org:
            return f"bounced: sender may not reply to case #{case_id}"
        posted = desk.post_comment(robot, case_id, CommentDraft(intent.body, False))
        if isinstance(posted, Denied):
            return f"refused: {posted.rule}"
        desk.move_case(robot, case_id, "reply")  # pulls a waiting case back (HD-3)
    for name in intent.attachments:
        desk.attach(robot, case_id, AttachmentDraft(name))
    return f"filed on case #{case_id}"


# -- the demo desk, seeded THROUGH the kernel as the real personas --------------

SEED = [
    ("dana", CaseDraft("Login broken for SSO users", "acme", "high", date(2026, 8, 20)),
     [("sam", "triage"), ("sam", "assign"),
      ("dana", "comment", "Affects every SSO user since the 09:00 deploy — "
                          "password logins still fine."),
      ("dana", "attach", "har_trace.har"),
      ("sam", "internal", "Suspect SAML clock skew after last night's cert rotation.")]),
    ("priya", CaseDraft("Export CSV garbled", "acme", "low", date(2026, 9, 1)), []),
    ("dana", CaseDraft("Billing double-charge", "acme", "high", date(2026, 8, 25)),
     [("sam", "triage"), ("sam", "assign"),
      ("sam", "comment", "Can you attach the card statement for the second charge?"),
      ("sam", "wait"), ("dana", "attach", "statement_march.pdf"),
      ("dana", "comment", "Statement attached — the duplicate is row 14.")]),
    ("priya", CaseDraft("Webhook retries misfire", "acme", "med", date(2026, 8, 30)),
     [("sam", "triage"), ("sam", "assign"), ("sam", "resolve")]),
    ("dana", CaseDraft("Onboarding email typo", "acme", "low", date(2026, 8, 1)),
     [("sam", "triage"), ("sam", "assign"), ("dana", "attach", "welcome_email.png"),
      ("noor", "internal", "Fixed in template v2; closing after QA."),
      ("noor", "resolve"), ("noor", "close")]),
    ("omar", CaseDraft("API 500s on bulk upload", "zephyr", "high", date(2026, 8, 16)),
     [("sam", "triage"), ("sam", "assign"),
      ("omar", "comment", "Fails for batches over 1k rows; single rows are fine."),
      ("omar", "attach", "bulk_upload_500.log")]),
    ("omar", CaseDraft("SSO metadata rotation", "zephyr", "med", date(2026, 9, 20)), []),
    ("omar", CaseDraft("Sandbox reset requests hang", "zephyr", "low", date(2026, 8, 28)),
     [("quinn", "triage"), ("quinn", "assign"), ("quinn", "wait")]),
]

SEED_MAIL = [
    B.Email("priya@acme.example", "Fwd: cannot reset password",
            "The reset link says 'expired' immediately.", ["reset_screenshot.png"]),
    B.Email("dana@acme.example", "Re: [#1] Login broken for SSO users",
            "Also seeing it on the EU tenant.", []),
]


def seed(desk: Desk) -> int:
    """Every seeded fact goes through the kernel: a seed that violates the
    policy cannot exist (it would come back Denied and fail here)."""
    def must(got: object) -> object:
        if got is None or isinstance(got, Denied):
            raise RuntimeError(f"seed refused: {got}")
        return got

    for creator, draft, moves in SEED:
        case = must(desk.open_case(desk.actor(creator), draft))
        for who, what, *arg in moves:
            a = desk.actor(who)
            if what == "assign":
                must(desk.edit_case(a, case.id, CasePatch(assignee=who)))
            elif what in ("comment", "internal"):
                must(desk.post_comment(a, case.id, CommentDraft(arg[0], what == "internal")))
            elif what == "attach":
                must(desk.attach(a, case.id, AttachmentDraft(arg[0])))
            else:
                must(desk.move_case(a, case.id, what))
    for mail in SEED_MAIL:
        receive_mail(desk, mail)
    return len(desk.visible_cases(desk.actor("noor")))


# -- HTTP -------------------------------------------------------------------------

def make_handler(desk: Desk):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def persona(self) -> Actor:
            jar = cookies_mod.SimpleCookie(self.headers.get("Cookie") or "")
            return desk.actor(jar["persona"].value if "persona" in jar else None)

        def send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8",
                 extra: dict[str, str] | None = None) -> None:
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def page(self, actor: Actor, view: View, notice: B.Notice | None, status: int) -> None:
            content, status = render(desk, actor, view, notice, status)
            current = view.queue if isinstance(view, B.ShowQueue) else None
            if self.headers.get("HX-Request") == "true":
                side = B.sidebar(current, True, desk.view(actor), B.sort_into_queues, esc)
                return self.send(status, content + side)
            side = B.sidebar(current, False, desk.view(actor), B.sort_into_queues, esc)
            self.send(status, B.document(side, content))

        def form(self) -> dict[str, str]:
            n = int(self.headers.get("Content-Length") or 0)
            q = urllib.parse.parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
            return {k: v[0] for k, v in q.items()}

        def handle_request(self, method: str) -> None:
            url = urllib.parse.urlparse(self.path)
            if method == "GET" and url.path == "/static/htmx.min.js":
                return self.send(200, (STATIC / "htmx.min.js").read_text(),
                                 "application/javascript")
            form = self.form() if method == "POST" else {}
            if method == "POST" and url.path == "/inbound-mail":
                return self.inbound_mail(form)
            actor = self.persona()
            query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                cmd = B.route(B.HttpRequest(method, url.path, query, form))
                if isinstance(cmd, B.SwitchPersona):
                    who = desk.actor(cmd.name)
                    return self.send(303, "", extra={
                        "Location": "/", "Set-Cookie": f"persona={who.name}; Path=/"})
                view, notice, status = apply(desk, actor, cmd)
                return self.page(actor, view, notice, status)
            except (BoxError, ContractViolation) as e:
                # a generated body failed: say which box, never a traceback
                return self.send(500, f"<pre>{esc(str(e))}</pre>")

        def inbound_mail(self, form: dict[str, str]) -> None:
            token = self.headers.get("X-Relay-Mail-Token") or ""
            if not hmac.compare_digest(token, MAIL_TOKEN):
                return self.send(401, "bad mail token", "text/plain")
            mail = B.Email(form.get("sender", ""), form.get("subject", ""),
                           form.get("body", ""),
                           [f for f in form.get("attachments", "").split(",")])
            try:
                return self.send(200, receive_mail(desk, mail), "text/plain")
            except (BoxError, ContractViolation) as e:
                return self.send(500, str(e), "text/plain")

        def do_GET(self) -> None:
            self.handle_request("GET")

        def do_POST(self) -> None:
            self.handle_request("POST")

    return Handler


def build(port: int) -> tuple[Desk, ThreadingHTTPServer]:
    desk = Desk(TODAY, PEOPLE)
    return desk, ThreadingHTTPServer(("127.0.0.1", port), make_handler(desk))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8811)
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()
    desk, httpd = build(args.port)
    try:
        n = seed(desk)
        print(f"Relay (boxes) is up: http://127.0.0.1:{httpd.server_address[1]}/  "
              f"({n} cases seeded through the kernel; desk date {desk.today})", flush=True)
        if not args.seed_only:
            httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
