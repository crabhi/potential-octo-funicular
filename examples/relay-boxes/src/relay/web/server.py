"""REVIEWED — the HTTP server: plumbing, and the one place where a request's
typed command becomes a kernel call.

    uv run relay                  # serve on :8811 with a seeded desk
    uv run relay --port 0         # ephemeral port
    uv run relay --seed-only      # boot, seed, print summary, exit

A request flows: `route` (box) parses it into a typed view/command →
`apply` (here) turns a command into ONE kernel call as the cookie's
persona → the page boxes render the result, reading the kernel through
the persona's read-only DeskReader. No HTML is written here and no
product decision is made here.
"""

from __future__ import annotations

import argparse
import hmac
import html
import pathlib
import sys
import urllib.parse
from http import cookies as cookies_mod
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boxkit import BoxError, ContractViolation
from relay.cases.model import Case
from relay.cases.pages import case_page, new_case_page, queue_page
from relay.cases.queues import sort_into_queues
from relay.kernel import Desk
from relay.mail.gateway import MAIL_TOKEN, receive_mail
from relay.mail.model import Email
from relay.people import Actor
from relay.policy import Denied
from relay.web.routes import (
    AttachFile,
    EditCase,
    HttpRequest,
    Invalid,
    MoveCase,
    OpenCase,
    PostComment,
    RedactComment,
    RemoveAttachment,
    Route,
    ShowCase,
    ShowNewCase,
    ShowQueue,
    SwitchPersona,
    route,
)
from relay.web.seed import PEOPLE, TODAY, seed
from relay.web.ui import Notice, document, sidebar

STATIC = pathlib.Path(__file__).resolve().parent / "static"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


View = ShowQueue | ShowCase | ShowNewCase


def refused(d: Denied) -> Notice:
    return Notice("refused", d.reason, d.rule)


def apply(desk: Desk, actor: Actor, cmd: Route) -> tuple[View, Notice | None, int]:
    """One typed command → one kernel call. Returns the page to show next,
    the notice for it, and the HTTP status."""
    if isinstance(cmd, (ShowQueue, ShowCase, ShowNewCase)):
        return cmd, None, 200
    if isinstance(cmd, Invalid):
        return cmd.back, Notice("invalid", cmd.message), 422
    if isinstance(cmd, OpenCase):
        got = desk.open_case(actor, cmd.draft)
        if isinstance(got, Denied):
            return ShowNewCase(), refused(got), 403
        return ShowCase(got.id), Notice("ok", f"Case #{got.id} opened."), 200

    if isinstance(cmd, EditCase):
        case_id, got, ok = cmd.case_id, desk.edit_case(actor, cmd.case_id, cmd.patch), "Changes saved."
    elif isinstance(cmd, MoveCase):
        case_id, got, ok = cmd.case_id, desk.move_case(actor, cmd.case_id, cmd.action), f"{cmd.action} — done."
    elif isinstance(cmd, PostComment):
        case_id, got, ok = cmd.case_id, desk.post_comment(actor, cmd.case_id, cmd.draft), "Posted to the thread."
    elif isinstance(cmd, AttachFile):
        case_id, got, ok = cmd.case_id, desk.attach(actor, cmd.case_id, cmd.draft), "Evidence attached."
    elif isinstance(cmd, RedactComment):
        case_id, got, ok = cmd.case_id, desk.act_on_comment(actor, cmd.comment_id, "redact"), "Comment redacted."
    elif isinstance(cmd, RemoveAttachment):
        case_id, got, ok = cmd.case_id, desk.act_on_attachment(actor, cmd.attachment_id, "remove"), "Attachment removed."
    else:  # NotFound, or SwitchPersona reaching here by mistake
        return ShowQueue("inbox"), None, 404

    if got is None:
        return ShowQueue("inbox"), None, 404
    if isinstance(got, Denied):
        return ShowCase(case_id), refused(got), 403
    return ShowCase(case_id), Notice("ok", ok), 200


def render(desk: Desk, actor: Actor, view: View, notice: Notice | None,
           status: int) -> tuple[str, int]:
    """Main-column HTML for a view, as `actor` sees it."""
    reader = desk.view(actor)
    if isinstance(view, ShowCase):
        got = desk.get_case(actor, view.case_id)
        if isinstance(got, Case):
            return case_page(view.case_id, notice, reader, esc), status
        notice = refused(got) if isinstance(got, Denied) else notice
        view, status = ShowQueue("inbox"), (403 if isinstance(got, Denied) else 404)
    if isinstance(view, ShowNewCase):
        return new_case_page(notice, reader, esc), status
    return queue_page(view.queue, notice, reader, sort_into_queues, esc), status


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

        def page(self, actor: Actor, view: View, notice: Notice | None, status: int) -> None:
            content, status = render(desk, actor, view, notice, status)
            current = view.queue if isinstance(view, ShowQueue) else None
            if self.headers.get("HX-Request") == "true":
                side = sidebar(current, True, desk.view(actor), sort_into_queues, esc)
                return self.send(status, content + side)
            side = sidebar(current, False, desk.view(actor), sort_into_queues, esc)
            self.send(status, document(side, content))

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
                cmd = route(HttpRequest(method, url.path, query, form))
                if isinstance(cmd, SwitchPersona):
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
            mail = Email(form.get("sender", ""), form.get("subject", ""),
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
