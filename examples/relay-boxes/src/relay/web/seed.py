"""REVIEWED — the demo desk: personas, and cases seeded THROUGH the kernel as
the real personas (a seed that violates policy cannot exist)."""

from __future__ import annotations

from datetime import date

from relay.cases.model import CaseDraft, CasePatch
from relay.kernel import Desk
from relay.mail.gateway import receive_mail
from relay.mail.model import Email
from relay.people import Actor
from relay.policy import Denied
from relay.thread.model import AttachmentDraft, CommentDraft

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
    Email("priya@acme.example", "Fwd: cannot reset password",
            "The reset link says 'expired' immediately.", ["reset_screenshot.png"]),
    Email("dana@acme.example", "Re: [#1] Login broken for SSO users",
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
