"""REVIEWED — who may do what in a case's thread and evidence (HD-8/9).
The parent case's live state and org decide; the kernel joins it in."""

from __future__ import annotations

from relay.policy import CHILDREN, POLICY, Situation


@POLICY.deny("org_walls_thread", """HD-1 via HD-8/9: the org wall extends to a
    case's thread and evidence — the PARENT case's org decides.""", on=CHILDREN)
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and not s.same_org

@POLICY.deny("sealed_thread", """HD-8/9 + HD-6: a closed case seals its thread
    and its evidence — nothing new is said, redacted, attached or removed; the
    record stays readable forever.""", on=CHILDREN)
def _(s: Situation) -> bool:
    return s.case.state == "closed" and s.action != "read"

@POLICY.deny("comment_needs_body", "HD-8: a comment needs a body.", on=("comment",))
def _(s: Situation) -> bool:
    return s.action == "post" and s.comment is not None and not s.comment.body.strip()

@POLICY.deny("internal_is_staff_only", """HD-8: internal notes never reach
    customers or the robot — not readable, not postable, not anything.""",
    on=("comment",))
def _(s: Situation) -> bool:
    return s.comment is not None and s.comment.internal and not s.staff

@POLICY.deny("fresh_evidence_only", """HD-9: a resolved or closed case takes no
    new evidence — dispute the resolution first.""", on=("attachment",))
def _(s: Situation) -> bool:
    return s.action == "attach" and s.case.state in ("resolved", "closed")

@POLICY.deny("attachment_needs_file", "HD-9: an attachment needs a filename.",
             on=("attachment",))
def _(s: Situation) -> bool:
    return (s.action == "attach" and s.attachment is not None
            and not s.attachment.filename.strip())

@POLICY.allow("customer_discusses", "HD-8: customers read and join their org's "
              "case threads.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action in ("read", "post")

@POLICY.allow("staff_discuss", "HD-8: staff read and join every thread, internal "
              "notes included.", on=("comment",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "post")

@POLICY.allow("lead_redacts", "HD-8: if something must disappear, a lead redacts "
              "it — and the redaction stays on the record.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "redact"

@POLICY.allow("mailbot_files_mail", "HD-8: the robot files inbound email bodies "
              "as comments — it never reads the thread back.", on=("comment",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action == "post"

@POLICY.allow("customer_attaches", "HD-9: customers read and add their org's "
              "evidence.", on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action in ("read", "attach")

@POLICY.allow("staff_attach", "HD-9: staff read and add evidence on every case.",
              on=("attachment",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "attach")

@POLICY.allow("author_removes", "HD-9: a mistaken upload is removed by the person "
              "who attached it (removal keeps the tombstone).", on=("attachment",))
def _(s: Situation) -> bool:
    return (s.action == "remove" and s.attachment is not None
            and s.attachment.author == s.actor.name
            and s.actor.role in ("customer", "agent", "lead"))

@POLICY.allow("lead_removes", "HD-9: a lead removes anyone's mistaken upload.",
              on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "remove"

@POLICY.allow("mailbot_attaches", "HD-9: the robot files email attachments — and "
              "never removes or reads anything.", on=("attachment",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action == "attach"
