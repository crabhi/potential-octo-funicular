# boxkit: generated implementation of `sidebar` against spec f3bbe7e19e541eaf
# boxkit: generated implementation of `document` against spec f36cfa2e0a4856c3



def _person_label(p: Actor, esc: Escape) -> str:
    label = p.name + " (" + p.role
    if p.org:
        label = label + " · " + p.org
    label = label + ")"
    return esc(label)


def sidebar(current: QueueKey | None, oob: bool, desk: DeskReader, sort: QueueSorter, esc: Escape) -> str:
    queues = sort(desk.cases(), desk.today())
    me = desk.me()

    links = []
    for q in queues:
        key = esc(q.key)
        cls = "nav-link"
        if current is not None and q.key == current:
            cls = cls + " current"
        if q.key == "breached":
            cls = cls + " alert"
        aria = ""
        if current is not None and q.key == current:
            aria = ' aria-current="page"'
        links.append(
            '<a class="' + cls + '" href="/?q=' + key + '" hx-get="/?q=' + key + '"'
            ' hx-target="#content" hx-push-url="true"' + aria + ">"
            "<span>" + esc(q.label) + "</span>"
            '<span class="count">' + str(len(q.case_ids)) + "</span></a>"
        )

    options = []
    anon_sel = ""
    if me.role == "anonymous":
        anon_sel = " selected"
    options.append('<option value=""' + anon_sel + ">anonymous</option>")
    for p in desk.people():
        if p.role == "anonymous":
            continue
        sel = ""
        if me.role != "anonymous" and p.name == me.name:
            sel = " selected"
        options.append('<option value="' + esc(p.name) + '"' + sel + ">" + _person_label(p, esc) + "</option>")

    oob_attr = ""
    if oob:
        oob_attr = ' hx-swap-oob="true"'

    return (
        '<aside id="sidebar" class="sidebar"' + oob_attr + ">"
        '<div class="brand">Relay<span>.</span></div>'
        '<nav class="nav">' + "".join(links) + "</nav>"
        '<button type="button" class="btn-new" hx-get="/new" hx-target="#content" hx-push-url="true">+ New case</button>'
        '<form class="persona" method="post" action="/persona" hx-post="/persona" hx-trigger="change" hx-target="#content">'
        '<label for="persona-select">Viewing as</label>'
        '<select id="persona-select" name="persona">'
        + "".join(options)
        + "</select>"
        "<noscript><button type=\"submit\" class=\"btn btn-small\">Switch</button></noscript>"
        "</form>"
        '<div class="deskdate">Desk date ' + esc(str(desk.today())) + "</div>"
        "</aside>"
    )


def _css() -> str:
    return """
:root{
  --side:#16202e; --side-2:#1f2c3f; --side-text:#c5d0df; --side-dim:#8294ab;
  --bg:#f4f6f9; --card:#ffffff; --ink:#1c2533; --dim:#5f6b7d; --line:#dfe4ec;
  --accent:#2563eb; --accent-d:#1d4ed8;
  --high:#dc2626; --med:#f59e0b; --low:#16a34a;
  --alert:#b91c1c; --alert-bg:#fee2e2;
  --ok:#166534; --ok-bg:#dcfce7; --warn:#92400e; --warn-bg:#fef3c7;
  --note-bg:#fff8e1; --note-line:#f0d98a;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);display:flex;min-height:100vh}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1{font-size:22px;margin:0 0 4px;line-height:1.25}
h2{font-size:13px;margin:0 0 10px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
p{margin:0 0 8px}

/* sidebar */
.sidebar{width:240px;flex:0 0 240px;background:var(--side);color:var(--side-text);padding:18px 14px;display:flex;flex-direction:column;gap:18px;position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{font-size:20px;font-weight:700;color:#fff;letter-spacing:.02em;padding:0 8px}
.brand span{color:#60a5fa}
.nav{display:flex;flex-direction:column;gap:2px}
.nav-link{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:6px;color:var(--side-text);cursor:pointer}
.nav-link:hover{background:var(--side-2);text-decoration:none;color:#fff}
.nav-link.current{background:var(--accent);color:#fff;font-weight:600}
.nav-link.alert{color:#fecaca}
.nav-link.alert .count{background:var(--high);color:#fff}
.nav-link.alert.current{background:var(--alert);color:#fff}
.count{min-width:24px;text-align:center;padding:1px 8px;border-radius:999px;background:var(--side-2);color:var(--side-text);font-size:12px;font-weight:600}
.nav-link.current .count{background:rgba(255,255,255,.22);color:#fff}
.btn-new{display:block;width:100%;text-align:center;padding:9px 10px;border-radius:6px;border:0;background:#fff;color:var(--side);font-weight:700;cursor:pointer;font-size:14px}
.btn-new:hover{background:#e2e8f0}
.persona{margin-top:auto;border-top:1px solid var(--side-2);padding-top:14px}
.persona label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--side-dim);margin-bottom:6px}
.persona select{width:100%;padding:7px 8px;border-radius:6px;border:1px solid #33445c;background:var(--side-2);color:#fff;font-size:13px}
.deskdate{font-size:12px;color:var(--side-dim);padding:0 8px}

/* main column */
#content{flex:1;min-width:0;padding:26px 34px 60px;max-width:1100px}
.page-head{margin-bottom:16px}
.count-line{color:var(--dim);margin:0 0 14px}
.back{display:inline-block;margin-bottom:12px;font-size:13px}

/* toasts */
.toast{display:flex;gap:10px;align-items:baseline;padding:10px 14px;border-radius:8px;margin-bottom:16px;border:1px solid;animation:toastin .25s ease-out}
.toast-ok{background:var(--ok-bg);color:var(--ok);border-color:#86efac}
.toast-refused{background:var(--alert-bg);color:var(--alert);border-color:#fca5a5}
.toast-invalid{background:var(--warn-bg);color:var(--warn);border-color:#fcd34d}
.toast-head{font-weight:700;white-space:nowrap}
.toast code{background:rgba(0,0,0,.07);padding:1px 6px;border-radius:4px;font-size:12px}
@keyframes toastin{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}

/* severity dots, pills */
.sev{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--dim)}
.sev::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--dim)}
.sev-high::before{background:var(--high)}
.sev-med::before{background:var(--med)}
.sev-low::before{background:var(--low)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#e5e7eb;color:#374151;text-transform:capitalize}
.pill-new{background:#dbeafe;color:#1e40af}
.pill-open{background:#e0e7ff;color:#3730a3}
.pill-waiting{background:#fef3c7;color:#92400e}
.pill-resolved{background:#dcfce7;color:#166534}
.pill-closed{background:#e5e7eb;color:#4b5563}

/* tables */
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.tbl th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);background:#f8fafc;padding:9px 12px;border-bottom:1px solid var(--line)}
.tbl td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
.tbl tr:last-child td{border-bottom:0}
.tbl tbody tr.row{cursor:pointer}
.tbl tbody tr.row:hover{background:#f1f5ff}
.tbl .subject{font-weight:600}
.muted{color:var(--dim)}
.sla{white-space:nowrap}
.sla-over{color:var(--alert);font-weight:700}
.sla-over small{background:var(--alert-bg);padding:1px 6px;border-radius:4px;margin-left:6px;font-weight:600}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:8px;padding:30px;text-align:center;color:var(--dim)}

/* cards */
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin-bottom:16px}
.case-head{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;margin-bottom:12px}
.meta-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px 18px;margin:0}
.meta-grid dt{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.meta-grid dd{margin:2px 0 0;font-weight:500}

/* buttons and forms */
.btn{display:inline-block;padding:7px 14px;border-radius:6px;border:1px solid var(--line);background:#fff;color:var(--ink);font-size:13px;font-weight:600;cursor:pointer}
.btn:hover{background:#f1f5f9}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accent-d)}
.btn-small{padding:2px 9px;font-size:12px;font-weight:600}
.btn-locked{border-style:dashed;color:var(--dim);background:#f8fafc}
.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
details.locked{margin-top:12px;border:1px dashed var(--line);border-radius:8px;padding:8px 12px;background:#fafbfc}
details.locked summary{cursor:pointer;color:var(--dim);font-size:13px;font-weight:600}
.locked-list{list-style:none;margin:10px 0 2px;padding:0;display:flex;flex-direction:column;gap:8px}
.locked-list li{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.rule{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:#eef2f7;color:#374151;padding:1px 6px;border-radius:4px}
.lockline{color:var(--dim);font-size:13px;margin:8px 0 0}
.form{display:grid;gap:12px}
.form-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.field{display:flex;flex-direction:column;gap:4px}
.field label{font-size:12px;font-weight:600;color:var(--dim)}
.field input,.field select,.field textarea,.form textarea{padding:8px 10px;border:1px solid #c9d1de;border-radius:6px;font:inherit;background:#fff;color:var(--ink);width:100%}
.field input:focus,.field select:focus,.field textarea:focus,.form textarea:focus{outline:2px solid #bfdbfe;border-color:var(--accent)}
.field input[readonly]{background:#f1f5f9;color:var(--dim)}
.field-static{padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:#f1f5f9;color:var(--ink)}
.check{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--dim)}
.form-foot{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.hint{color:var(--dim);font-size:12px}
.edit-box{margin-top:14px}

/* thread and evidence */
.thread{display:flex;flex-direction:column;gap:10px;margin-bottom:12px}
.comment{background:var(--card);border:1px solid var(--line);border-left:4px solid #94a3b8;border-radius:8px;padding:10px 14px}
.comment.internal{background:var(--note-bg);border-color:var(--note-line);border-left-color:#d97706}
.comment-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--dim);margin-bottom:4px}
.comment-head .who{font-weight:700;color:var(--ink);font-size:13px}
.tag-internal{background:#d97706;color:#fff;border-radius:4px;padding:0 7px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.comment-body{white-space:pre-wrap;word-wrap:break-word}
.comment-actions{display:flex;gap:6px;margin-top:8px}
.tombstone{border:1px dashed #cbd5e1;background:#f8fafc;color:var(--dim);font-style:italic;border-radius:8px;padding:10px 14px}
.tombstone .comment-head{font-style:normal}
.evidence-list{list-style:none;margin:0 0 12px;padding:0;display:flex;flex-direction:column;gap:8px}
.att{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:9px 14px}
.att .file{font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.att.tombstone{font-style:italic}
.section{margin-top:22px}
@media (max-width:760px){
  body{flex-direction:column}
  .sidebar{width:100%;height:auto;position:static;flex:none}
  #content{padding:18px 14px 40px}
  .tbl{font-size:13px}
}
"""


def _swap_script() -> str:
    return """
document.addEventListener('htmx:beforeSwap', function (e) {
  var s = e.detail.xhr ? e.detail.xhr.status : 0;
  if (s === 403 || s === 404 || s === 422) {
    e.detail.shouldSwap = true;
    e.detail.isError = false;
  }
});
"""


def document(sidebar_html: str, content_html: str) -> str:
    head = (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Relay — support desk</title>\n"
        '<script src="/static/htmx.min.js"></script>\n'
        "<style>" + _css() + "</style>\n"
        "<script>" + _swap_script() + "</script>\n"
        "</head>\n"
    )
    body = (
        "<body>\n"
        + sidebar_html
        + '\n<main id="content">'
        + content_html
        + "</main>\n</body>\n</html>\n"
    )
    return head + body
