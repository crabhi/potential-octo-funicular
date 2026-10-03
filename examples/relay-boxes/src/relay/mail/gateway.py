"""REVIEWED — the mail gateway (HD-7): the outer code that turns what the
robot made of an email (relay.mail.intake, a black box) into kernel calls
as the robot. Also the org directory the box receives as a capability."""

from __future__ import annotations

import os

from relay.kernel import Desk
from relay.mail.intake import intake_email
from relay.mail.model import Email, MailBounce, MailNewCase
from relay.policy import Denied
from relay.thread.model import AttachmentDraft, CommentDraft

ORG_DOMAINS = {"acme.example": "acme", "zephyr.example": "zephyr"}
MAIL_TOKEN = os.environ.get("RELAY_MAIL_TOKEN", "dev-mail-token")


def org_of(address: str) -> str | None:
    return ORG_DOMAINS.get(address.rsplit("@", 1)[-1].strip().lower().rstrip(">"))


def receive_mail(desk: Desk, mail: Email) -> str:
    """Interpret one email (box), then act on it as the robot (here)."""
    robot = desk.actor("postbot")
    intent = intake_email(mail, org_of)
    if isinstance(intent, MailBounce):
        return f"bounced: {intent.reason}"
    if isinstance(intent, MailNewCase):
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
