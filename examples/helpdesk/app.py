"""Relay — a customer-support helpdesk whose UI is hand-written and FREE,
while every interaction is guarded by the rule base behind the kernel.

    python app.py                 # serve on :8810, seed a demo desk, stay up
    python app.py --port 0        # ephemeral port
    python app.py --seed-only     # boot, seed, print summary, exit (for CI)

The division of labor (guardrail 10):

  * `rulesets/helpdesk/` decides WHO MAY DO WHAT. It is analyzed by Z3
    against a frozen gate and enforced by engine.kernel — the only
    doorway to state this file has (`from engine import kernel`, held
    mechanically by analysis.boundary in check.sh).
  * THIS file decides how the product looks and feels, and it answers to
    nobody: custom queues (including "SLA breached", a cross-state view a
    generic UI cannot invent), severity chips, htmx partial swaps, a
    persona switcher. Redesign it at will — no policy lives here.

The UI *reflects* decisions (allowed actions are buttons, refused ones sit
in a "locked" list naming their rule, still clickable on purpose) but
never *makes* them: hide a button, forge a request — the kernel refuses
identically, and the toast names the rule.
"""

import argparse
import datetime
import html
import pathlib
import re
import sys
import tempfile
import urllib.parse
from http import cookies as cookies_mod
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rule-driven-cms"))

from engine import kernel  # the ONLY engine import — see analysis.boundary

RULES_DIR = HERE / "rulesets" / "helpdesk"
STATIC = HERE / "static"
TODAY = "2026-08-14"

# ---------------------------------------------------------------------------
# The demo desk, seeded THROUGH the kernel as the real personas: a seed that
# violates policy cannot exist. (Case 6 is breached, so the seed itself is
# forced to route its resolution through the lead — try seeding it as sam.
# Likewise every thread below is written BEFORE its case closes: sealed_thread
# refuses late seed comments exactly as it refuses late real ones.)
# Moves: (actor, action), (actor, "edit", {updates}),
#        (actor, "comment", {body[, internal]}), (actor, "attach", {filename}).
SEED = [
    ("dana", {"subject": "Login broken for SSO users", "org": "acme",
              "severity": "high", "sla_due": "2026-08-20"},
     [("sam", "triage"), ("sam", "edit", {"assignee": "sam"}),
      ("dana", "comment", {"body": "Affects every SSO user since the 09:00 "
                                   "deploy — password logins still fine."}),
      ("dana", "attach", {"filename": "har_trace.har"}),
      ("sam", "comment", {"body": "Suspect SAML clock skew after last "
                                  "night's cert rotation.", "internal": "yes"}),
      ("postbot", "comment", {"body": "Fwd: user report — login loop on "
                                      "the EU tenant."})]),
    ("priya", {"subject": "Export CSV garbled", "org": "acme",
               "severity": "low", "sla_due": "2026-09-01"}, []),
    ("postbot", {"subject": "Fwd: cannot reset password", "org": "acme",
                 "severity": "med", "sla_due": "2026-08-12"}, []),
    ("dana", {"subject": "Billing double-charge", "org": "acme",
              "severity": "high", "sla_due": "2026-08-25"},
     [("sam", "triage"), ("sam", "edit", {"assignee": "sam"}),
      ("sam", "comment", {"body": "Can you attach the card statement for "
                                  "the second charge?"}),
      ("sam", "wait"),
      ("dana", "attach", {"filename": "statement_march.pdf"}),
      ("dana", "comment", {"body": "Statement attached — the duplicate is "
                                   "row 14."})]),
    ("priya", {"subject": "Webhook retries misfire", "org": "acme",
               "severity": "med", "sla_due": "2026-08-30"},
     [("sam", "triage"), ("sam", "edit", {"assignee": "sam"}),
      ("sam", "resolve")]),
    ("dana", {"subject": "Onboarding email typo", "org": "acme",
              "severity": "low", "sla_due": "2026-08-01"},
     [("sam", "triage"), ("sam", "edit", {"assignee": "sam"}),
      ("dana", "attach", {"filename": "welcome_email.png"}),
      ("noor", "comment", {"body": "Fixed in template v2; closing after "
                                   "QA.", "internal": "yes"}),
      ("noor", "resolve"), ("noor", "close")]),
    ("omar", {"subject": "API 500s on bulk upload", "org": "zephyr",
              "severity": "high", "sla_due": "2026-08-16"},
     [("sam", "triage"), ("sam", "edit", {"assignee": "sam"}),
      ("omar", "comment", {"body": "Fails for batches over 1k rows; single "
                                   "rows are fine."}),
      ("omar", "attach", {"filename": "bulk_upload_500.log"})]),
    ("omar", {"subject": "SSO metadata rotation", "org": "zephyr",
              "severity": "med", "sla_due": "2026-09-20"}, []),
    ("omar", {"subject": "Sandbox reset requests hang", "org": "zephyr",
              "severity": "low", "sla_due": "2026-08-28"},
     [("quinn", "triage"), ("quinn", "edit", {"assignee": "quinn"}),
      ("quinn", "wait")]),
]


def seed(desk):
    made = 0
    for creator, fields, moves in SEED:
        actor = desk.actor(creator)
        row = desk.create(actor, fields)
        made += 1
        for move in moves:
            who, what = desk.actor(move[0]), move[1]
            if what == "edit":
                desk.edit(who, row["id"], move[2])
            elif what == "comment":
                desk.create(who, move[2], entity="comment",
                            parent_id=row["id"])
            elif what == "attach":
                desk.create(who, move[2], entity="attachment",
                            parent_id=row["id"])
            else:
                desk.act(who, what, row["id"])
    return made


# ---------------------------------------------------------------------------
# Presentation — all of it custom, none of it policy.

esc = lambda v: html.escape(str(v), quote=True)  # noqa: E731

STATE_META = {  # label, pill color
    "new": ("inbox", "#B96A00"), "open": ("working", "#2F5FD0"),
    "waiting": ("on hold", "#8A5A00"), "resolved": ("resolved", "#1E7B45"),
    "closed": ("closed", "#5C6474"),
}
SEV = {"high": ("#D64545", "high"), "med": ("#C08A3E", "med"),
       "low": ("#7C8AA0", "low")}
ACTION_LABEL = {"triage": "Triage ▸ working", "wait": "Put on hold",
                "reply": "File reply", "resolve": "Resolve",
                "reopen": "Reopen", "close": "Close (QA)"}

QUEUES = [
    ("inbox", "Inbox", lambda r, t: r["state"] == "new"),
    ("working", "Working", lambda r, t: r["state"] == "open"),
    ("waiting", "On hold", lambda r, t: r["state"] == "waiting"),
    ("breached", "SLA breached", lambda r, t: is_breached(r, t)
        and r["state"] in ("new", "open", "waiting")),
    ("resolved", "Resolved", lambda r, t: r["state"] == "resolved"),
    ("closed", "Closed", lambda r, t: r["state"] == "closed"),
]


def is_breached(row, today):
    return bool(row["sla_due"]) and today is not None and row["sla_due"] < today


def days_over(row, today):
    try:
        d = (datetime.date.fromisoformat(today)
             - datetime.date.fromisoformat(row["sla_due"])).days
        return f"{d}d over" if d > 0 else ""
    except ValueError:
        return ""


CSS = """
* { box-sizing: border-box; margin: 0; }
body { font: 14px/1.5 -apple-system, 'Segoe UI', Roboto, Helvetica, Arial,
       sans-serif; background: #F4F5F9; color: #21242E; display: flex;
       min-height: 100vh; }
a { color: inherit; text-decoration: none; }
aside { width: 232px; flex-shrink: 0; background: #191B26; color: #C9CDDB;
        padding: 18px 14px; display: flex; flex-direction: column; gap: 4px; }
aside .brand { font-size: 17px; font-weight: 800; color: #fff;
               letter-spacing: .02em; margin-bottom: 2px; }
aside .brand b { color: #8B7CFF; }
aside .sub { font-size: 11px; color: #6E7385; margin-bottom: 14px; }
aside .q { display: flex; align-items: center; gap: 8px; padding: 7px 10px;
           border-radius: 8px; font-size: 13.5px; cursor: pointer;
           color: #C9CDDB; }
aside .q:hover { background: #242736; }
aside .q.on { background: #2C2F42; color: #fff; font-weight: 600; }
aside .q .n { margin-left: auto; font-size: 11.5px; background: #2C2F42;
              border-radius: 9px; padding: 1px 8px; color: #9AA0B5; }
aside .q.breach { color: #F0A3A3; }
aside .q.breach .n { background: #4A2020; color: #F0A3A3; }
aside .newbtn { margin: 12px 0 4px; background: #6C5CE7; border: none;
                color: #fff; font: inherit; font-weight: 600; padding: 8px;
                border-radius: 8px; cursor: pointer; }
aside .newbtn:hover { background: #5A4BD1; }
aside .persona { margin-top: auto; border-top: 1px solid #2C2F42;
                 padding-top: 12px; font-size: 12px; color: #9AA0B5; }
aside .persona select { width: 100%; margin-top: 6px; background: #242736;
                        color: #E8EAF2; border: 1px solid #3A3E52;
                        border-radius: 6px; padding: 5px; font: inherit; }
aside .persona .date { margin-top: 8px; color: #6E7385; font-size: 11px; }
main { flex: 1; padding: 22px 28px; max-width: 1060px; }
h1 { font-size: 18px; margin-bottom: 2px; }
.crumb { color: #7A8092; font-size: 12.5px; margin-bottom: 14px; }
.toast { border-radius: 9px; padding: 10px 14px; margin-bottom: 14px;
         font-size: 13.5px; }
.toast.deny { background: #FBE9E9; border: 1px solid #E5B4B4; color: #8A2A2A; }
.toast.ok { background: #E6F3EA; border: 1px solid #B4D6BE; color: #22643A; }
.toast code { font-weight: 700; }
.toast .why { display: block; color: #6E7385; margin-top: 2px; }
table.cases { width: 100%; border-collapse: collapse; background: #fff;
              border-radius: 12px; overflow: hidden;
              box-shadow: 0 1px 3px rgba(20,22,35,.10); }
table.cases th { text-align: left; font-size: 11.5px; text-transform:
                 uppercase; letter-spacing: .05em; color: #7A8092;
                 padding: 10px 14px; border-bottom: 1px solid #ECEEF4;
                 background: #FAFBFD; }
table.cases td { padding: 11px 14px; border-bottom: 1px solid #F1F3F8;
                 font-size: 13.5px; }
table.cases tr.row { cursor: pointer; }
table.cases tr.row:hover td { background: #F6F5FF; }
.sev { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
       color: #5C6474; }
.sev i { width: 8px; height: 8px; border-radius: 4px; display: inline-block; }
.pill { display: inline-block; color: #fff; border-radius: 10px;
        padding: 1px 9px; font-size: 11.5px; white-space: nowrap; }
.org { display: inline-block; border: 1px solid #D7DAE5; color: #5C6474;
       border-radius: 6px; padding: 0 7px; font-size: 11.5px;
       background: #FAFBFD; }
.sla { font-size: 12px; color: #7A8092; white-space: nowrap; }
.sla.late { color: #C43D3D; font-weight: 700; }
.empty { color: #7A8092; padding: 32px; text-align: center; background: #fff;
         border-radius: 12px; box-shadow: 0 1px 3px rgba(20,22,35,.08); }
.case { background: #fff; border-radius: 12px; padding: 20px 24px;
        box-shadow: 0 1px 3px rgba(20,22,35,.10); max-width: 760px; }
.case h1 { font-size: 19px; }
.meta { display: grid; grid-template-columns: 120px 1fr 120px 1fr;
        gap: 7px 10px; margin: 16px 0; font-size: 13px; }
.meta dt { color: #7A8092; } .meta dd { font-weight: 500; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 6px; }
.actions button { font: inherit; font-weight: 600; border: none;
                  border-radius: 8px; padding: 7px 16px; cursor: pointer;
                  background: #6C5CE7; color: #fff; }
.actions button:hover { background: #5A4BD1; }
.actions button.quiet { background: #EDEEF5; color: #3A3E52; }
.actions button.quiet:hover { background: #E0E2EE; }
details.locked { margin: 10px 0 4px; font-size: 12.5px; color: #7A8092; }
details.locked summary { cursor: pointer; }
details.locked div { margin: 8px 0 0 4px; display: flex; flex-direction:
                     column; gap: 6px; }
details.locked button { font: inherit; font-size: 12px; border: 1px dashed
                        #C9CDDB; background: #FAFBFD; color: #7A8092;
                        border-radius: 7px; padding: 4px 10px; cursor:
                        pointer; text-align: left; }
details.locked code { color: #8A2A2A; }
form.edit { display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
            margin-top: 16px; border-top: 1px solid #ECEEF4;
            padding-top: 14px; }
form.edit label { font-size: 12px; color: #7A8092; display: block; }
form.edit input, form.edit select { width: 100%; font: inherit;
    padding: 6px 9px; border: 1px solid #D7DAE5; border-radius: 7px;
    margin-top: 3px; background: #fff; }
form.edit .wide { grid-column: 1 / -1; }
form.edit button { grid-column: 1 / -1; justify-self: start; font: inherit;
    font-weight: 600; background: #21242E; color: #fff; border: none;
    border-radius: 8px; padding: 7px 16px; cursor: pointer; }
.hintline { font-size: 12px; color: #9AA0B5; margin-top: 10px; }
.thread, .evidence { margin-top: 18px; border-top: 1px solid #ECEEF4;
                     padding-top: 12px; }
.thread h2, .evidence h2 { font-size: 11.5px; text-transform: uppercase;
                           letter-spacing: .05em; color: #7A8092;
                           margin-bottom: 8px; }
.c { border: 1px solid #ECEEF4; border-radius: 9px; padding: 8px 12px;
     margin-bottom: 8px; background: #FAFBFD; }
.c.internal { background: #FFF8E6; border-color: #EAD9A8; }
.c .who { font-size: 12px; color: #7A8092; margin-bottom: 3px;
          display: flex; align-items: center; gap: 8px; }
.c .who b { color: #3A3E52; }
.tag.int { background: #B96A00; color: #fff; border-radius: 8px;
           padding: 0 7px; font-size: 10.5px; }
.tomb { color: #9AA0B5; font-style: italic; }
.microbtn { margin-left: auto; font: inherit; font-size: 11px;
            border: 1px solid #D7DAE5; background: #fff; border-radius: 6px;
            padding: 1px 8px; cursor: pointer; color: #5C6474; }
.microbtn:hover { background: #F6F5FF; }
.att { display: flex; gap: 8px; align-items: center; font-size: 13px;
       padding: 6px 10px; border: 1px solid #ECEEF4; border-radius: 8px;
       margin-bottom: 6px; background: #FAFBFD; }
.att .who { color: #7A8092; font-size: 12px; }
form.say { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
form.say textarea { font: inherit; padding: 7px 10px; border: 1px solid
                    #D7DAE5; border-radius: 8px; resize: vertical; }
form.say .row2 { display: flex; align-items: center; gap: 14px; }
form.say button, form.attach button { font: inherit; font-weight: 600;
    background: #21242E; color: #fff; border: none; border-radius: 8px;
    padding: 6px 14px; cursor: pointer; }
form.attach { display: flex; gap: 8px; margin-top: 8px; }
form.attach input { flex: 1; font: inherit; padding: 6px 9px;
                    border: 1px solid #D7DAE5; border-radius: 7px; }
.chk { font-size: 12px; color: #8A5A00; }
"""


def page(desk, actor, content):
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Relay — support desk</title>
<script src="/static/htmx.min.js"></script>
<style>{CSS}</style></head>
<body hx-boost="false">
{sidebar(desk, actor)}
<main id="content">{content}</main>
<script>
// refusals are honest 403s; htmx skips 4xx swaps by default — opt back in
// so the kernel's named refusal lands in the page like any other response
document.body.addEventListener('htmx:beforeSwap', function (e) {{
  if (e.detail.xhr.status === 403 || e.detail.xhr.status === 404) {{
    e.detail.shouldSwap = true; e.detail.isError = false;
  }}
}});
</script>
</body></html>"""


def sidebar(desk, actor, oob=False):
    visible = desk.visible(actor)
    links = []
    for key, label, pred in QUEUES:
        n = sum(1 for r in visible if pred(r, desk.today))
        cls = "q breach" if key == "breached" else "q"
        links.append(
            f'<a class="{cls}" hx-get="/?q={key}" hx-target="#content" '
            f'hx-push-url="true">{esc(label)}<span class="n">{n}</span></a>')
    who = []
    for u in desk.users():
        sel = " selected" if u.name == actor.name else ""
        org = f" · {esc(u.attrs.get('org'))}" if u.attrs.get("org") else ""
        who.append(f'<option value="{esc(u.name)}"{sel}>'
                   f'{esc(u.name)} ({esc(u.role)}{org})</option>')
    who.append(f'<option value=""{" selected" if actor.role == "anonymous" else ""}>'
               f'anonymous</option>')
    return f"""<aside id="sidebar"{' hx-swap-oob="true"' if oob else ''}>
  <div class="brand">◗ <b>Relay</b></div>
  <div class="sub">support desk · rules-guarded</div>
  {''.join(links)}
  <button class="newbtn" hx-get="/new" hx-target="#content"
          hx-push-url="true">+ New case</button>
  <div class="persona">signed in as
    <form method="post" action="/persona">
      <select name="persona" onchange="this.form.submit()">{''.join(who)}</select>
    </form>
    <div class="date">desk date: {esc(desk.today)}</div>
  </div>
</aside>"""


def toast_deny(e):
    return (f'<div class="toast deny"><b>Refused</b> — rule '
            f'<code>{esc(e.rule.id)}</code>'
            f'<span class="why">{esc(e.rule.description)}</span></div>')


def toast_ok(msg):
    return f'<div class="toast ok">{esc(msg)}</div>'


def sev_html(row):
    color, label = SEV.get(row["severity"], ("#9AA0B5", row["severity"] or "—"))
    return f'<span class="sev"><i style="background:{color}"></i>{esc(label)}</span>'


def state_html(state):
    label, color = STATE_META.get(state, (state, "#5C6474"))
    return f'<span class="pill" style="background:{color}">{esc(label)}</span>'


def sla_html(desk, row):
    if not row["sla_due"]:
        return '<span class="sla">—</span>'
    if is_breached(row, desk.today) and row["state"] not in ("resolved", "closed"):
        return (f'<span class="sla late">⚠ {esc(row["sla_due"])} '
                f'({esc(days_over(row, desk.today))})</span>')
    return f'<span class="sla">due {esc(row["sla_due"])}</span>'


def queue_view(desk, actor, qkey, flash=""):
    qkey = qkey if qkey in {k for k, _, _ in QUEUES} else "inbox"
    label, pred = next((lb, p) for k, lb, p in QUEUES if k == qkey)
    rows = [r for r in desk.visible(actor) if pred(r, desk.today)]
    body = []
    for r in rows:
        body.append(f"""<tr class="row" hx-get="/case/{r['id']}"
 hx-target="#content" hx-push-url="true">
 <td>{sev_html(r)}</td>
 <td><b>{esc(r['subject']) or f"case #{r['id']}"}</b></td>
 <td><span class="org">{esc(r['org']) or '—'}</span></td>
 <td>{state_html(r['state'])}</td>
 <td>{esc(r['assignee']) or '<span style="color:#B0B5C6">unassigned</span>'}</td>
 <td>{sla_html(desk, r)}</td></tr>""")
    table = (f'<table class="cases"><tr><th>sev</th><th>case</th><th>org</th>'
             f'<th>state</th><th>assignee</th><th>SLA</th></tr>'
             f'{"".join(body)}</table>' if body else
             f'<div class="empty">Nothing in “{esc(label)}” — as seen by '
             f'{esc(actor.name)}. The list is the read rule.</div>')
    return (f'{flash}<h1>{esc(label)}</h1><div class="crumb">{len(rows)} '
            f'case(s) · what {esc(actor.name)} may see, nothing more</div>'
            f'{table}')


def detail_view(desk, actor, row, flash=""):
    allowed, locked = [], []
    for action, d in desk.affordances(actor, row):
        if action in ("edit", "delete"):
            continue  # edit has its form below; delete has no UI at all
        label = ACTION_LABEL.get(action, action)
        if d.allowed:
            allowed.append(
                f'<button hx-post="/case/{row["id"]}/act" '
                f'hx-vals=\'{{"action": "{esc(action)}"}}\' '
                f'hx-target="#content">{esc(label)}</button>')
        else:
            locked.append(
                f'<button hx-post="/case/{row["id"]}/act" '
                f'hx-vals=\'{{"action": "{esc(action)}"}}\' '
                f'hx-target="#content">🔒 {esc(label)} — refused by '
                f'<code>{esc(d.rule.id)}</code> (press to see)</button>')
    d_edit = desk.decide(actor, "edit", row)
    mine_btn = ""
    if actor.role in ("agent", "lead") and d_edit.allowed \
            and row["assignee"] != actor.name:
        mine_btn = (f'<button class="quiet" hx-post="/case/{row["id"]}/edit" '
                    f'hx-vals=\'{{"assignee": "{esc(actor.name)}"}}\' '
                    f'hx-target="#content">Assign to me</button>')
    locked_html = ""
    if locked:
        locked_html = (f'<details class="locked"><summary>{len(locked)} locked '
                       f'action(s) — the kernel refuses these for '
                       f'{esc(actor.name)}</summary><div>{"".join(locked)}'
                       f'</div></details>')
    sev_opts = "".join(
        f'<option value="{v}"{" selected" if row["severity"] == v else ""}>{v}'
        f'</option>' for v in ("high", "med", "low"))
    edit_form = f"""<form class="edit" hx-post="/case/{row['id']}/edit"
 hx-target="#content">
 <label class="wide">subject<input name="subject" value="{esc(row['subject'])}"></label>
 <label>assignee<input name="assignee" value="{esc(row['assignee'])}"></label>
 <label>severity<select name="severity">{sev_opts}</select></label>
 <label>SLA due<input type="date" name="sla_due" value="{esc(row['sla_due'])}"></label>
 <label>org<input name="org" value="{esc(row['org'])}"></label>
 <button>Save changes</button>
</form>""" if d_edit.allowed else (
        f'<p class="hintline">🔒 editing is refused right now by '
        f'<code>{esc(d_edit.rule.id if d_edit.rule else "the lifecycle")}</code>.</p>')
    return f"""{flash}<div class="crumb"><a hx-get="/" hx-target="#content"
 hx-push-url="true" style="cursor:pointer">← queues</a> / case #{row['id']}</div>
<div class="case">
 <h1>{esc(row['subject']) or f"case #{row['id']}"}</h1>
 <div style="margin-top:6px">{state_html(row['state'])}
   <span class="org">{esc(row['org']) or 'no org'}</span> {sla_html(desk, row)}</div>
 <dl class="meta">
  <dt>requester</dt><dd>{esc(row['author'])}</dd>
  <dt>assignee</dt><dd>{esc(row['assignee']) or 'unassigned'}</dd>
  <dt>severity</dt><dd>{sev_html(row)}</dd>
  <dt>case id</dt><dd>#{row['id']}</dd>
 </dl>
 <div class="actions">{''.join(allowed)}{mine_btn}</div>
 {locked_html}
 {edit_form}
 {thread_html(desk, actor, row)}
 <p class="hintline">Buttons are affordances, not permissions: every press —
 including the locked ones — is decided by the rules inside the kernel.
 The thread and the evidence are child entities of this case: their rules
 see the case's live state, so closing the case seals them by rule, not
 by UI code.</p>
</div>"""


def thread_html(desk, actor, row):
    """HD-8/9 rendered: the thread and the evidence. Every list here is a
    kernel read decision (an internal note simply isn't in a customer's
    list), every button an affordance, and both forms are mere suggestions —
    a forged POST meets the same rules. All of this is presentation:
    the seal, the walls and the screens live in rulesets/, not here."""
    comments = desk.visible(actor, entity="comment", parent_id=row["id"])
    items = []
    for c in comments:
        tag = ' <span class="tag int">internal</span>' if c["internal"] else ""
        body = ('<span class="tomb">✕ redacted by a lead — the tombstone '
                'stays on the record</span>'
                if c["state"] == "redacted" else esc(c["body"]))
        btns = "".join(
            f'<button class="microbtn" hx-post="/comment/{c["id"]}/act" '
            f'hx-vals=\'{{"action": "{esc(a)}", "case": "{row["id"]}"}}\' '
            f'hx-target="#content">{esc(a)}</button>'
            for a, d in desk.affordances(actor, c, entity="comment") if d.allowed)
        items.append(f'<div class="c{" internal" if c["internal"] else ""}">'
                     f'<div class="who"><b>{esc(c["author"])}</b>{tag}{btns}</div>'
                     f'<div>{body}</div></div>')
    probe = desk.decide(actor, "post", entity="comment", parent=row,
                        new_fields={"body": "x", "internal": ""})
    if probe.allowed:
        internal_box = ""
        if actor.role in ("agent", "lead"):  # presentation choice, not policy
            internal_box = ('<label class="chk"><input type="checkbox" '
                            'name="internal" value="yes"> internal note '
                            '(never reaches the customer)</label>')
        say = (f'<form class="say" hx-post="/case/{row["id"]}/comment" '
               f'hx-target="#content">'
               f'<textarea name="body" rows="2" placeholder="Write to the '
               f'thread…"></textarea><div class="row2"><button>Post</button>'
               f'{internal_box}</div></form>')
    else:
        say = (f'<p class="hintline">🔒 posting is refused right now by '
               f'<code>{esc(probe.rule.id if probe.rule else "the lifecycle")}'
               f'</code>.</p>')

    atts = desk.visible(actor, entity="attachment", parent_id=row["id"])
    files = []
    for a in atts:
        gone = a["state"] == "removed"
        name = (f'<span class="tomb">✕ {esc(a["filename"])} (removed)</span>'
                if gone else f'📎 <b>{esc(a["filename"])}</b>')
        btns = "".join(
            f'<button class="microbtn" hx-post="/attachment/{a["id"]}/act" '
            f'hx-vals=\'{{"action": "{esc(act)}", "case": "{row["id"]}"}}\' '
            f'hx-target="#content">{esc(act)}</button>'
            for act, d in desk.affordances(actor, a, entity="attachment")
            if d.allowed)
        files.append(f'<div class="att">{name}'
                     f'<span class="who">by {esc(a["author"])}</span>{btns}</div>')
    aprobe = desk.decide(actor, "attach", entity="attachment", parent=row,
                         new_fields={"filename": "x"})
    if aprobe.allowed:
        drop = (f'<form class="attach" hx-post="/case/{row["id"]}/attach" '
                f'hx-target="#content"><input name="filename" '
                f'placeholder="filename, e.g. trace.log"><button>Attach'
                f'</button></form>')
    else:
        drop = (f'<p class="hintline">🔒 new evidence is refused right now by '
                f'<code>{esc(aprobe.rule.id if aprobe.rule else "the lifecycle")}'
                f'</code>.</p>')
    return (f'<div class="thread"><h2>Thread ({len(items)})</h2>'
            f'{"".join(items) or "<p class=hintline>No comments yet.</p>"}{say}</div>'
            f'<div class="evidence"><h2>Evidence ({len(files)})</h2>'
            f'{"".join(files) or "<p class=hintline>No files.</p>"}{drop}</div>')


def new_view(desk, actor, flash=""):
    org = actor.attrs.get("org", "")
    org_input = (f'<span class="org">{esc(org)}</span>'
                 f'<input type="hidden" name="org" value="{esc(org)}">'
                 if org else '<input name="org" placeholder="acme">')
    return f"""{flash}<div class="crumb"><a hx-get="/" hx-target="#content"
 hx-push-url="true" style="cursor:pointer">← queues</a> / new case</div>
<div class="case"><h1>Open a case</h1>
<form class="edit" hx-post="/case" hx-target="#content">
 <label class="wide">subject<input name="subject" autofocus
        placeholder="What is broken?"></label>
 <label>severity<select name="severity"><option>high</option>
   <option selected>med</option><option>low</option></select></label>
 <label>SLA due<input type="date" name="sla_due"></label>
 <label>org {org_input}</label>
 <button>Open case</button>
</form>
<p class="hintline">The form suggests; the rules decide (a case without a
subject, or outside your org, is refused by name).</p></div>"""


# ---------------------------------------------------------------------------
# HTTP plumbing — routing and cookies only; no decisions.

def make_handler(desk):
    route_case = re.compile(r"^/case/(\d+)$")
    route_act = re.compile(r"^/case/(\d+)/(act|edit|comment|attach)$")
    route_child = re.compile(r"^/(comment|attachment)/(\d+)/act$")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        # -- plumbing -------------------------------------------------------
        def persona(self):
            jar = cookies_mod.SimpleCookie(self.headers.get("Cookie") or "")
            name = jar["persona"].value if "persona" in jar else ""
            return desk.actor(name) or desk.actor(None)

        def is_htmx(self):
            return self.headers.get("HX-Request") == "true"

        def respond(self, actor, content, code=200):
            """Partial for htmx requests, full shell otherwise. Mutations
            also refresh the sidebar counts out-of-band."""
            if self.is_htmx():
                body = content + sidebar(desk, actor, oob=True)
            else:
                body = page(desk, actor, content)
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def form(self):
            n = int(self.headers.get("Content-Length") or 0)
            q = urllib.parse.parse_qs(self.rfile.read(n).decode())
            return {k: v[0] for k, v in q.items()}

        def redirect(self, path, set_cookie=None):
            self.send_response(303)
            self.send_header("Location", path)
            if set_cookie is not None:
                self.send_header("Set-Cookie", f"persona={set_cookie}; Path=/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def send_static(self, name):
            f = STATIC / name
            if not f.is_file():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                return self.end_headers()
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)

        # -- routes ----------------------------------------------------------
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path.startswith("/static/"):
                return self.send_static(url.path.rsplit("/", 1)[1])
            actor = self.persona()
            q = urllib.parse.parse_qs(url.query)
            if url.path == "/":
                return self.respond(actor, queue_view(desk, actor,
                                                      q.get("q", ["inbox"])[0]))
            if url.path == "/new":
                return self.respond(actor, new_view(desk, actor))
            m = route_case.match(url.path)
            if m:
                try:
                    row = desk.get(actor, m.group(1))
                except kernel.Denied as e:
                    return self.respond(
                        actor, queue_view(desk, actor, "inbox", toast_deny(e)),
                        code=403)
                if row is None:
                    return self.respond(actor, queue_view(desk, actor, "inbox"),
                                        code=404)
                return self.respond(actor, detail_view(desk, actor, row))
            return self.respond(actor, queue_view(desk, actor, "inbox"), code=404)

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            form = self.form()
            if url.path == "/persona":
                return self.redirect("/", set_cookie=form.get("persona", ""))
            actor = self.persona()
            if url.path == "/case":
                try:
                    row = desk.create(actor, form)
                except kernel.Denied as e:
                    return self.respond(actor, new_view(desk, actor,
                                                        toast_deny(e)), code=403)
                return self.respond(actor, detail_view(
                    desk, actor, row, toast_ok(f"case #{row['id']} opened")))
            m = route_act.match(url.path)
            mc = route_child.match(url.path)
            if not m and not mc:
                return self.respond(actor, queue_view(desk, actor, "inbox"),
                                    code=404)
            case_id = int(m.group(1) if m else form.get("case", 0))
            try:
                if mc:  # a transition on a thread/evidence row (e.g. redact)
                    entity, child_id = mc.group(1), int(mc.group(2))
                    action = form.get("action", "")
                    if action not in desk.rb.entity_of(entity).actions:
                        return self.respond(actor,
                                            queue_view(desk, actor, "inbox"),
                                            code=404)
                    desk.act(actor, action, child_id, entity=entity)
                    row = desk.get(actor, case_id)
                    flash = toast_ok(f"{action} — done")
                elif m.group(2) == "comment":
                    desk.create(actor, {"body": form.get("body", ""),
                                        "internal": form.get("internal", "")},
                                entity="comment", parent_id=case_id)
                    row = desk.get(actor, case_id)
                    flash = toast_ok("posted to the thread")
                elif m.group(2) == "attach":
                    desk.create(actor, {"filename": form.get("filename", "")},
                                entity="attachment", parent_id=case_id)
                    row = desk.get(actor, case_id)
                    flash = toast_ok("evidence attached")
                elif m.group(2) == "edit":
                    row = desk.edit(actor, case_id, form)
                    flash = toast_ok("changes saved")
                else:
                    action = form.get("action", "")
                    if action not in desk.rb.actions:
                        return self.respond(actor,
                                            queue_view(desk, actor, "inbox"),
                                            code=404)
                    row = desk.act(actor, action, case_id)
                    flash = toast_ok(f"{ACTION_LABEL.get(action, action)} — done")
            except KeyError:
                return self.respond(actor, queue_view(desk, actor, "inbox"),
                                    code=404)
            except kernel.Illegal as e:
                row = desk.get(actor, case_id)
                flash = (f'<div class="toast deny">the lifecycle has no '
                         f'<code>{esc(e.action)}</code> from this state</div>')
            except kernel.Denied as e:
                # the case may not even be readable; fall back to the queue
                try:
                    row = desk.get(actor, case_id)
                except kernel.Denied:
                    row = None
                if row is None:
                    return self.respond(
                        actor, queue_view(desk, actor, "inbox", toast_deny(e)),
                        code=403)
                return self.respond(actor,
                                    detail_view(desk, actor, row, toast_deny(e)),
                                    code=403)
            return self.respond(actor, detail_view(desk, actor, row, flash))

    return Handler


def build(db_path, port):
    """Boot the kernel on the rule base and put the UI in front of it."""
    desk = kernel.boot(RULES_DIR, db_path, today=TODAY,
                       seed=RULES_DIR / "features.yaml")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(desk))
    return desk, httpd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8810)
    ap.add_argument("--db", help="database path (default: a fresh temp file)")
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()

    tmp = None
    db = args.db
    if not db:
        tmp = tempfile.TemporaryDirectory()
        db = f"{tmp.name}/relay.db"
    desk, httpd = build(db, args.port)
    try:
        n = seed(desk)
        print(f"Relay is up: http://127.0.0.1:{httpd.server_address[1]}/  "
              f"({n} cases seeded through the kernel; desk date {desk.today})",
              flush=True)
        if args.seed_only:
            return 0
        httpd.serve_forever()
    finally:
        httpd.server_close()
        if tmp:
            tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
