# boxkit: generated implementation of `new_case_page` against spec ad5a1dcad87e9717


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


def new_case_page(notice: Notice | None, desk: DeskReader, esc: Escape) -> str:
    me = desk.me()
    if me.org:
        org_field = (
            '<div class="field"><label>Organisation</label>'
            '<div class="field-static">' + esc(me.org) + "</div>"
            '<input type="hidden" name="org" value="' + esc(me.org) + '"></div>'
        )
    else:
        org_field = (
            '<div class="field"><label for="nc-org">Organisation</label>'
            '<input id="nc-org" type="text" name="org" required placeholder="e.g. acme"></div>'
        )

    return (
        _toast(notice, esc)
        + '<a class="back" href="/" hx-get="/" hx-target="#content" hx-push-url="true">← queues</a>'
        '<div class="page-head"><h1>Open a case</h1>'
        '<p class="muted">Opening as ' + esc(me.name) + ".</p></div>"
        '<div class="card"><form class="form" method="post" action="/case" hx-post="/case" hx-target="#content">'
        '<div class="field"><label for="nc-subject">Subject</label>'
        '<input id="nc-subject" type="text" name="subject" required placeholder="What is going wrong?"></div>'
        '<div class="form-row">'
        '<div class="field"><label for="nc-sev">Severity</label>'
        '<select id="nc-sev" name="severity">'
        '<option value="high">high</option><option value="med" selected>med</option><option value="low">low</option>'
        "</select></div>"
        '<div class="field"><label for="nc-sla">SLA due</label>'
        '<input id="nc-sla" type="date" name="sla_due"></div>'
        + org_field
        + "</div>"
        '<div class="form-foot"><button type="submit" class="btn btn-primary">Open case</button></div>'
        "</form></div>"
    )
