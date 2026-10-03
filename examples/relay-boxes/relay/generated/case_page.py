# boxkit: generated implementation of `case_page` against spec a460f8a937830c08

import json


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


def _vals(d: dict, esc: Escape) -> str:
    # JSON for hx-vals, escaped for a double-quoted attribute.
    return esc(json.dumps(d))


def _post_button(url: str, vals: dict, label: str, cls: str, title: str, esc: Escape) -> str:
    t = ""
    if title:
        t = ' title="' + esc(title) + '"'
    return (
        '<button type="button" class="' + cls + '" hx-post="' + url + '" hx-vals="' + _vals(vals, esc) + '"'
        ' hx-target="#content"' + t + ">" + esc(label) + "</button>"
    )


def _rule_tag(rule: str | None, esc: Escape) -> str:
    if rule:
        return '<span class="rule">' + esc(rule) + "</span>"
    return '<span class="rule">no rule named</span>'


def _refusal_line(what: str, a: Affordance, esc: Escape) -> str:
    reason = ""
    if a.reason:
        reason = " " + esc(a.reason)
    return '<p class="lockline">' + esc(what) + " is locked by rule " + _rule_tag(a.rule, esc) + "." + reason + "</p>"


def _case_actions(case: Case, desk: DeskReader, esc: Escape) -> str:
    cid = str(case.id)
    url = "/case/" + cid + "/act"
    allowed = []
    locked = []
    for a in desk.case_actions(case.id):
        if a.allowed:
            allowed.append(_post_button(url, {"action": a.action}, a.action, "btn btn-primary", "", esc))
        else:
            why = ""
            if a.reason:
                why = a.reason
            li = (
                "<li>" + _post_button(url, {"action": a.action}, a.action, "btn btn-locked", why, esc)
                + " " + _rule_tag(a.rule, esc)
            )
            if a.reason:
                li = li + ' <span class="hint">' + esc(a.reason) + "</span>"
            locked.append(li + "</li>")
    out = '<div class="card"><h2>Actions</h2>'
    if allowed:
        out = out + '<div class="actions">' + "".join(allowed) + "</div>"
    else:
        out = out + '<p class="muted">No actions available right now.</p>'
    if locked:
        out = out + (
            '<details class="locked"><summary>' + str(len(locked)) + " locked</summary>"
            '<ul class="locked-list">' + "".join(locked) + "</ul></details>"
        )
    return out + "</div>"


def _edit_card(case: Case, desk: DeskReader, esc: Escape) -> str:
    cid = str(case.id)
    me = desk.me()
    aff = desk.may_edit(case.id)
    if not aff.allowed:
        return '<div class="card">' + _refusal_line("Editing", aff, esc) + "</div>"
    sevs = []
    for s in ["high", "med", "low"]:
        sel = ""
        if s == case.severity:
            sel = " selected"
        sevs.append('<option value="' + s + '"' + sel + ">" + s + "</option>")
    assignee = ""
    if case.assignee:
        assignee = case.assignee
    sla = ""
    if case.sla_due is not None:
        sla = str(case.sla_due)
    out = (
        '<div class="card"><h2>Edit case</h2>'
        '<form class="form" method="post" action="/case/' + cid + '/edit" hx-post="/case/' + cid + '/edit" hx-target="#content">'
        '<div class="field"><label for="ed-subject">Subject</label>'
        '<input id="ed-subject" type="text" name="subject" value="' + esc(case.subject) + '"></div>'
        '<div class="form-row">'
        '<div class="field"><label for="ed-assignee">Assignee</label>'
        '<input id="ed-assignee" type="text" name="assignee" value="' + esc(assignee) + '"></div>'
        '<div class="field"><label for="ed-sev">Severity</label>'
        '<select id="ed-sev" name="severity">' + "".join(sevs) + "</select></div>"
        '<div class="field"><label for="ed-sla">SLA due</label>'
        '<input id="ed-sla" type="date" name="sla_due" value="' + esc(sla) + '"></div>'
        '<div class="field"><label for="ed-org">Organisation</label>'
        '<input id="ed-org" type="text" name="org" value="' + esc(case.org) + '"></div>'
        "</div>"
        '<div class="form-foot"><button type="submit" class="btn btn-primary">Save changes</button>'
    )
    is_staff = me.role == "agent" or me.role == "lead"
    if is_staff and case.assignee != me.name:
        out = out + _post_button(
            "/case/" + cid + "/edit", {"assignee": me.name}, "Assign to me", "btn", "", esc
        )
    return out + "</div></form></div>"


def _comment(c: Comment, desk: DeskReader, esc: Escape) -> str:
    who = '<span class="who">' + esc(c.author) + "</span>"
    if c.state == "redacted":
        return (
            '<div class="tombstone"><div class="comment-head">' + who + "</div>"
            "Comment redacted — the text has been withheld.</div>"
        )
    cls = "comment"
    tag = ""
    if c.internal:
        cls = "comment internal"
        tag = '<span class="tag-internal">internal</span>'
    btns = []
    for a in desk.comment_actions(c.id):
        if a.allowed:
            btns.append(
                _post_button(
                    "/comment/" + str(c.id) + "/" + a.action,
                    {"case": c.case_id},
                    a.action,
                    "btn btn-small",
                    "",
                    esc,
                )
            )
    acts = ""
    if btns:
        acts = '<div class="comment-actions">' + "".join(btns) + "</div>"
    return (
        '<div class="' + cls + '"><div class="comment-head">' + who + tag + "</div>"
        '<div class="comment-body">' + esc(c.body) + "</div>" + acts + "</div>"
    )


def _thread(case: Case, desk: DeskReader, esc: Escape) -> str:
    cid = str(case.id)
    items = []
    for c in desk.thread(case.id):
        items.append(_comment(c, desk, esc))
    out = '<div class="section"><h2>Thread</h2>'
    if items:
        out = out + '<div class="thread">' + "".join(items) + "</div>"
    else:
        out = out + '<div class="empty">No comments yet.</div>'
    pub = desk.may_post(case.id, False)
    if pub.allowed:
        internal = desk.may_post(case.id, True)
        box = ""
        if internal.allowed:
            box = '<label class="check"><input type="checkbox" name="internal" value="yes"> internal note</label>'
        out = out + (
            '<div class="card"><form class="form" method="post" action="/case/' + cid + '/comment"'
            ' hx-post="/case/' + cid + '/comment" hx-target="#content">'
            '<div class="field"><label for="cm-body">Add a comment</label>'
            '<textarea id="cm-body" name="body" rows="3" required></textarea></div>'
            '<div class="form-foot"><button type="submit" class="btn btn-primary">Post</button>' + box + "</div>"
            "</form></div>"
        )
    else:
        out = out + _refusal_line("Posting", pub, esc)
    return out + "</div>"


def _attachment(a: Attachment, desk: DeskReader, esc: Escape) -> str:
    who = '<span class="muted">added by ' + esc(a.author) + "</span>"
    if a.state == "removed":
        return '<li class="att tombstone">File removed ' + who + "</li>"
    btns = []
    for act in desk.attachment_actions(a.id):
        if act.allowed:
            btns.append(
                _post_button(
                    "/attachment/" + str(a.id) + "/" + act.action,
                    {"case": a.case_id},
                    act.action,
                    "btn btn-small",
                    "",
                    esc,
                )
            )
    return (
        '<li class="att"><span class="file">' + esc(a.filename) + "</span> " + who
        + "".join(btns) + "</li>"
    )


def _evidence(case: Case, desk: DeskReader, esc: Escape) -> str:
    cid = str(case.id)
    items = []
    for a in desk.evidence(case.id):
        items.append(_attachment(a, desk, esc))
    out = '<div class="section"><h2>Evidence</h2>'
    if items:
        out = out + '<ul class="evidence-list">' + "".join(items) + "</ul>"
    else:
        out = out + '<div class="empty">No evidence attached.</div>'
    aff = desk.may_attach(case.id)
    if aff.allowed:
        out = out + (
            '<div class="card"><form class="form" method="post" action="/case/' + cid + '/attach"'
            ' hx-post="/case/' + cid + '/attach" hx-target="#content">'
            '<div class="field"><label for="at-file">Attach a file (filename)</label>'
            '<input id="at-file" type="text" name="filename" required placeholder="screenshot.png"></div>'
            '<div class="form-foot"><button type="submit" class="btn btn-primary">Attach</button></div>'
            "</form></div>"
        )
    else:
        out = out + _refusal_line("Attaching", aff, esc)
    return out + "</div>"


def case_page(case_id: int, notice: Notice | None, desk: DeskReader, esc: Escape) -> str:
    back = '<a class="back" href="/" hx-get="/" hx-target="#content" hx-push-url="true">← queues</a>'
    case = desk.case(case_id)
    if not isinstance(case, Case):
        return (
            _toast(notice, esc) + back
            + '<div class="empty">This case is not available.</div>'
        )

    assignee = '<span class="muted">unassigned</span>'
    if case.assignee:
        assignee = esc(case.assignee)
    sla = '<span class="muted">none</span>'
    if case.sla_due is not None:
        today = desk.today()
        live = case.state == "new" or case.state == "open" or case.state == "waiting"
        if live and case.sla_due < today:
            days = (today - case.sla_due).days
            sla = '<span class="sla-over">' + esc(str(case.sla_due)) + "<small>" + str(days) + " d over</small></span>"
        else:
            sla = esc(str(case.sla_due))

    head = (
        '<div class="card"><div class="case-head"><h1>' + esc(case.subject) + "</h1>"
        '<span class="pill pill-' + esc(case.state) + '">' + esc(case.state) + "</span></div>"
        '<dl class="meta-grid">'
        "<div><dt>Org</dt><dd>" + esc(case.org) + "</dd></div>"
        "<div><dt>Requester</dt><dd>" + esc(case.requester) + "</dd></div>"
        "<div><dt>Assignee</dt><dd>" + assignee + "</dd></div>"
        '<div><dt>Severity</dt><dd><span class="sev sev-' + esc(case.severity) + '">' + esc(case.severity) + "</span></dd></div>"
        "<div><dt>SLA</dt><dd>" + sla + "</dd></div>"
        "<div><dt>Case</dt><dd>#" + str(case.id) + "</dd></div>"
        "</dl></div>"
    )
    return (
        _toast(notice, esc) + back + head
        + _case_actions(case, desk, esc)
        + _edit_card(case, desk, esc)
        + _thread(case, desk, esc)
        + _evidence(case, desk, esc)
    )
