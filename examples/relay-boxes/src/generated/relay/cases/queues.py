# boxkit: generated implementation of `sort_into_queues` against spec 71cc8e59d16a837f
from datetime import date


def _rank(severity: str) -> int:
    if severity == "high":
        return 0
    if severity == "med":
        return 1
    return 2


def _ids(cases: list) -> list:
    ordered = sorted(cases, key=lambda c: (_rank(c.severity), c.id))
    return [c.id for c in ordered]


def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    inbox = [c for c in cases if c.state == "new"]
    working = [c for c in cases if c.state == "open"]
    waiting = [c for c in cases if c.state == "waiting"]
    breached = [
        c
        for c in cases
        if c.state in ("new", "open", "waiting")
        and c.sla_due is not None
        and c.sla_due < today
    ]
    resolved = [c for c in cases if c.state == "resolved"]
    closed = [c for c in cases if c.state == "closed"]
    return [
        Queue("inbox", "Inbox", _ids(inbox)),
        Queue("working", "Working", _ids(working)),
        Queue("waiting", "On hold", _ids(waiting)),
        Queue("breached", "SLA breached", _ids(breached)),
        Queue("resolved", "Resolved", _ids(resolved)),
        Queue("closed", "Closed", _ids(closed)),
    ]
