"""REVIEWED — interpreting one inbound email: a contract, body in
generated.relay.mail.intake. Acting on the result is the gateway's job
(relay.mail.gateway, reviewed)."""

from __future__ import annotations

from boxkit import blackbox
from relay.mail.model import Email, MailIntent, OrgDirectory


@blackbox
def intake_email(mail: Email, org_of: OrgDirectory) -> MailIntent:
    """HD-7: interpret one inbound email for the mail robot.

    For every outcome below, "body" means the email body with surrounding
    whitespace trimmed, and "attachments" the attachment names as given,
    dropping empty ones.

    A subject containing "[#<id>]" (anywhere) is a reply to case <id>:
    MailReply(id, body, attachments). Otherwise it opens a case:
    the sender's org is `org_of(mail.sender)` — if None, MailBounce naming
    the unknown sender. The case subject is the email subject with leading
    "Re:"/"Fwd:"/"Fw:" prefixes (any case, repeated) removed and whitespace
    trimmed; if that leaves nothing, MailBounce("empty subject"). Severity
    is "high" if the subject or body contains "urgent" or "outage" (any
    case), else "med"; sla_due is None (staff set it):
    MailNewCase(draft, body, attachments)."""
    ...
