# boxkit: generated implementation of `route` against spec c88820646243c5bb
import re
from datetime import date


_QUEUES = ("inbox", "working", "waiting", "breached", "resolved", "closed")


_SEVERITIES = ("high", "med", "low")


_ACTIONS = ("triage", "wait", "reply", "resolve", "reopen", "close")


_ID_RE = re.compile(r"[0-9]+")


_DATE_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


def _parse_id(text):
    """Positive decimal integer, else None."""
    if _ID_RE.fullmatch(text) is None:
        return None
    n = int(text)
    if n <= 0:
        return None
    return n


def _parse_date(text):
    """ISO date (YYYY-MM-DD) or None when malformed."""
    m = _DATE_RE.fullmatch(text.strip())
    if m is None:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _case_post(case_id, verb, form):
    back = ShowCase(case_id)
    if verb == "act":
        action = form.get("action", "")
        if action not in _ACTIONS:
            return Invalid("invalid action", back)
        return MoveCase(case_id, action)
    if verb == "edit":
        subject = form.get("subject")
        org = form.get("org")
        assignee = form.get("assignee")
        severity = None
        if "severity" in form:
            severity = form["severity"]
            if severity not in _SEVERITIES:
                return Invalid("invalid severity", back)
        sla_due = None
        raw = form.get("sla_due", "")
        if raw != "" and raw.strip() != "":
            sla_due = _parse_date(raw)
            if sla_due is None:
                return Invalid("invalid sla_due", back)
        return EditCase(
            case_id,
            CasePatch(
                subject=subject,
                org=org,
                severity=severity,
                assignee=assignee,
                sla_due=sla_due,
            ),
        )
    if verb == "comment":
        return PostComment(
            case_id,
            CommentDraft(body=form.get("body", ""), internal=form.get("internal") == "yes"),
        )
    if verb == "attach":
        return AttachFile(case_id, AttachmentDraft(filename=form.get("filename", "")))
    return NotFound()


def _post(parts, form):
    n = len(parts)
    if n == 1 and parts[0] == "case":
        severity = form.get("severity", "med")
        if severity not in _SEVERITIES:
            return Invalid("invalid severity", ShowNewCase())
        sla_due = None
        raw = form.get("sla_due", "")
        if raw.strip() != "":
            sla_due = _parse_date(raw)
            if sla_due is None:
                return Invalid("invalid sla_due", ShowNewCase())
        return OpenCase(
            CaseDraft(
                subject=form.get("subject", ""),
                org=form.get("org", ""),
                severity=severity,
                sla_due=sla_due,
            )
        )
    if n == 1 and parts[0] == "persona":
        return SwitchPersona(form.get("persona", ""))
    if n == 3 and parts[0] == "case" and parts[2] in ("act", "edit", "comment", "attach"):
        case_id = _parse_id(parts[1])
        if case_id is None:
            return NotFound()
        return _case_post(case_id, parts[2], form)
    if n == 3 and parts[0] == "comment" and parts[2] == "redact":
        cid = _parse_id(parts[1])
        if cid is None:
            return NotFound()
        case_id = _parse_id(form.get("case", ""))
        if case_id is None:
            return Invalid("invalid case", ShowQueue("inbox"))
        return RedactComment(case_id, cid)
    if n == 3 and parts[0] == "attachment" and parts[2] == "remove":
        aid = _parse_id(parts[1])
        if aid is None:
            return NotFound()
        case_id = _parse_id(form.get("case", ""))
        if case_id is None:
            return Invalid("invalid case", ShowQueue("inbox"))
        return RemoveAttachment(case_id, aid)
    return NotFound()


def _get(parts, query):
    n = len(parts)
    if n == 0:
        q = query.get("q", "")
        if q in _QUEUES:
            return ShowQueue(q)
        return ShowQueue("inbox")
    if n == 1 and parts[0] == "new":
        return ShowNewCase()
    if n == 2 and parts[0] == "case":
        case_id = _parse_id(parts[1])
        if case_id is None:
            return NotFound()
        return ShowCase(case_id)
    return NotFound()


def route(req):
    path = req.path
    if not path.startswith("/"):
        return NotFound()
    parts = [] if path == "/" else path[1:].split("/")
    if req.method == "GET":
        return _get(parts, req.query)
    if req.method == "POST":
        return _post(parts, req.form)
    return NotFound()
