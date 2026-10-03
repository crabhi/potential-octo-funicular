# boxkit: generated implementation of `intake_email` against spec 4b5c86ac65c9f63a
import re


def _case_id(subject):
    m = re.search(r"\[#(\d+)\]", subject)
    if m is None:
        return None
    return int(m.group(1))


def _strip_prefixes(subject):
    s = subject.strip()
    while True:
        m = re.match(r"(?i)(re|fwd|fw)\s*:", s)
        if m is None:
            break
        s = s[m.end():].strip()
    return s


def _keep_names(names):
    out = []
    for n in names:
        if n != "":
            out.append(n)
    return out


def intake_email(mail, org_of):
    body = mail.body.strip()
    attachments = _keep_names(mail.attachments)

    cid = _case_id(mail.subject)
    if cid is not None:
        return MailReply(cid, body, attachments)

    org = org_of(mail.sender)
    if org is None:
        return MailBounce("unknown sender: " + mail.sender)

    subject = _strip_prefixes(mail.subject)
    if subject == "":
        return MailBounce("empty subject")

    text = (mail.subject + "\n" + mail.body).lower()
    if "urgent" in text or "outage" in text:
        severity = "high"
    else:
        severity = "med"

    draft = CaseDraft(subject, org, severity, None)
    return MailNewCase(draft, body, attachments)
