"""REVIEWED — `intake_email` (relay.mail.intake): replies, new cases, bounces."""

from __future__ import annotations

from relay.cases.model import CaseDraft
from relay.mail.gateway import org_of
from relay.mail.intake import intake_email
from relay.mail.model import Email, MailBounce, MailNewCase, MailReply


def test_mail_reply_new_case_and_bounces():
    m = intake_email(Email("x@acme.example", "RE: [#12] still broken", "  more  ", ["a.png", ""]), org_of)
    assert m == MailReply(12, "more", ["a.png"])
    m = intake_email(Email("dana@acme.example", "Fwd: re: FW: Outage in EU", "help", []), org_of)
    assert m == MailNewCase(CaseDraft("Outage in EU", "acme", "high", None), "help", [])
    m = intake_email(Email("dana@acme.example", "Question", "is this URGENT?", []), org_of)
    assert isinstance(m, MailNewCase) and m.draft.severity == "high"
    m = intake_email(Email("dana@acme.example", "Question", "when?", []), org_of)
    assert isinstance(m, MailNewCase) and m.draft.severity == "med"
    assert isinstance(intake_email(Email("eve@evil.example", "hi", "", []), org_of), MailBounce)
    assert intake_email(Email("dana@acme.example", "Re: ", "x", []), org_of) == \
        MailBounce("empty subject")
