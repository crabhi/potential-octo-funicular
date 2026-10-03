# boxkit: generated implementation of `queue_page` against spec 8fcd004f2ae32df4

from datetime import date


def _toast(notice: Notice | None, esc: Escape) -> str:
    if notice is None:
        return ""
    if notice.kind == "refused":
        rule = notice.rule if notice.rule else "unknown"
        head = "Refused — rule <code>" + esc(rule) + "</code>"
        return (
            '<div class="toast toast-refused" role="alert"><span class="toast-head">' + head + "</span>"
            "<span>" + esc(notice.text) + "</span></div>"
        )
    if notice.kind == "invalid":
        return (
            '<div class="toast toast-invalid" role="alert"><span class="toast-head">Invalid</span>'
            "<span>" + esc(notice.text) + "</span></div>"
        )
    return (
        '<div class="toast toast-ok" role="status"><span class="toast-head">Done</span>'
        "<span>" + esc(notice.text) + "</span></div>"
    )


def _sla_cell(c: Case, today: date, esc: Escape) -> str:
    if c.sla_due is None:
        return '<td class="sla muted">—</td>'
    due = esc(str(c.sla_due))
    live = c.state == "new" or c.state == "open" or c.state == "waiting"
    if live and c.sla_due < today:
        days = (today - c.sla_due).days
        return '<td class="sla sla-over">' + due + "<small>" + str(days) + " d over</small></td>"
    return '<td class="sla">' + due + "</td>"


def _row(c: Case, today: date, esc: Escape) -> str:
    cid = str(c.id)
    assignee = '<span class="muted">unassigned</span>'
    if c.assignee:
        assignee = esc(c.assignee)
    return (
        '<tr class="row" hx-get="/case/' + cid + '" hx-target="#content" hx-push-url="true">'
        '<td><span class="sev sev-' + esc(c.severity) + '">' + esc(c.severity) + "</span></td>"
        '<td class="subject"><a href="/case/' + cid + '">' + esc(c.subject) + "</a>"
        ' <span class="muted">#' + cid + "</span></td>"
        "<td>" + esc(c.org) + "</td>"
        '<td><span class="pill pill-' + esc(c.state) + '">' + esc(c.state) + "</span></td>"
        "<td>" + assignee + "</td>"
        + _sla_cell(c, today, esc)
        + "</tr>"
    )


def queue_page(queue: QueueKey, notice: Notice | None, desk: DeskReader, sort: QueueSorter, esc: Escape) -> str:
    today = desk.today()
    cases = desk.cases()
    by_id = {}
    for c in cases:
        by_id[c.id] = c

    found = None
    for q in sort(cases, today):
        if q.key == queue:
            found = q
    if found is None:
        return _toast(notice, esc) + '<div class="page-head"><h1>Queue not found</h1></div><div class="empty">There is no such queue.</div>'

    rows = []
    for cid in found.case_ids:
        if cid in by_id:
            rows.append(_row(by_id[cid], today, esc))

    n = len(rows)
    if n == 1:
        count_line = "1 case"
    else:
        count_line = str(n) + " cases"

    out = _toast(notice, esc)
    out = out + '<div class="page-head"><h1>' + esc(found.label) + "</h1></div>"
    out = out + '<p class="count-line">' + count_line + "</p>"
    if n == 0:
        out = out + '<div class="empty">No cases in ' + esc(found.label) + ".</div>"
        return out
    out = out + (
        '<table class="tbl"><thead><tr>'
        "<th>Severity</th><th>Subject</th><th>Org</th><th>State</th><th>Assignee</th><th>SLA</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    return out
