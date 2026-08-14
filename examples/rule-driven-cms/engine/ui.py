"""A generic web UI, derived entirely from the rule base. Zero domain words.

    python -m engine.server --rules rulesets/<any> --db ... --ui

Serves, on top of the JSON API of server.py:

    /ui            board: one column per lifecycle state, cards the current
                   persona is allowed to read (the list IS the read rule)
    /ui/items/<id> detail: every structurally-legal action rendered as a
                   button — enabled iff the decision function allows it,
                   greyed with the denying rule named when it does not.
                   Denied buttons stay clickable on purpose: the UI never
                   enforces, it only *reflects* the decision function, and
                   pressing one shows the named refusal banner.
    /ui/new        create form (fields from the rule base)
    /ui/rules      the program: lifecycle, rules, assumptions, projections
    /ui/persona    switch identity (research demo: authn is out of scope)

Everything on screen is derived: columns from `states`, forms from
`fields`, buttons from `lifecycle` + the decision function, banners from
rule ids and their stakeholder descriptions. There is no template to edit
per app — a different rules.yaml is a different application.
"""

import html
import re
import urllib.parse
from http import cookies as cookies_mod

from . import features as features_mod
from . import rulebase as rb_mod
from . import server as server_mod
from . import store

PALETTE = ["#5B7DB1", "#C08A3E", "#7E57A5", "#3A7D44", "#B4552D",
           "#1F6F6B", "#8A5A83", "#5C6B7E"]

CSS = """
* { box-sizing: border-box; margin: 0; }
body { font: 14px/1.45 -apple-system, 'Segoe UI', Roboto, Helvetica, Arial,
       sans-serif; background: #EEF1F5; color: #1F2A3A; }
a { color: #1F6F6B; text-decoration: none; }
header { background: #1F2A3A; color: #fff; padding: 10px 22px;
         display: flex; align-items: center; gap: 14px; }
header .brand { font-weight: 700; font-size: 16px; }
header .brand span { color: #7FB5B2; }
header nav { display: flex; gap: 12px; font-size: 13px; }
header nav a { color: #AFC3CF; }
header form { margin-left: auto; display: flex; gap: 6px; align-items: center; }
header select, header button, .btn {
  font: inherit; border-radius: 6px; border: 1px solid #C9D3DE;
  padding: 4px 10px; background: #fff; cursor: pointer; }
.persona { background: #2E4156; color: #D8E2EA; padding: 3px 10px;
           border-radius: 12px; font-size: 12.5px; }
main { padding: 18px 22px; }
.banner { border-radius: 8px; padding: 10px 14px; margin: 0 0 14px;
          font-size: 13.5px; }
.banner.deny { background: #F6E3DA; border: 1px solid #DBA98F; color: #7C3A1D; }
.banner.ok { background: #E3EFE5; border: 1px solid #A9CBB0; color: #2C5E34; }
.banner code { font-weight: 700; }
.banner .why { color: #5C6B7E; display: block; margin-top: 2px; }
.board { display: flex; gap: 14px; align-items: flex-start; overflow-x: auto; }
.col { background: #E3E8EF; border-radius: 10px; padding: 10px;
       min-width: 215px; width: 215px; flex-shrink: 0; }
.col h2 { font-size: 12.5px; text-transform: uppercase; letter-spacing: .04em;
          color: #47566A; display: flex; align-items: center; gap: 7px;
          padding: 2px 4px 8px; }
.col h2 .dot { width: 9px; height: 9px; border-radius: 5px; display: inline-block; }
.col h2 .n { margin-left: auto; color: #7C8AA0; font-weight: 400; }
.card { background: #fff; border-radius: 8px; padding: 9px 11px;
        margin-bottom: 9px; box-shadow: 0 1px 2px rgba(31,42,58,.12);
        border-top: 3px solid transparent; }
.card .t { font-weight: 600; margin-bottom: 2px; }
.card .m { color: #5C6B7E; font-size: 12px; }
.card .acts { margin-top: 7px; display: flex; flex-wrap: wrap; gap: 5px; }
.chip { font-size: 11.5px; border-radius: 6px; padding: 2px 9px;
        border: 1px solid transparent; cursor: pointer; }
.chip.go { background: #1F6F6B; color: #fff; }
.chip.no { background: #F0F2F5; color: #9AA7B7; border-color: #D8DFE7;
           text-decoration: line-through; }
.detail { background: #fff; border-radius: 10px; padding: 18px 22px;
          max-width: 640px; box-shadow: 0 1px 3px rgba(31,42,58,.12); }
.detail h1 { font-size: 19px; margin-bottom: 4px; }
.state-badge { display: inline-block; color: #fff; border-radius: 12px;
               padding: 2px 11px; font-size: 12px; }
dl { display: grid; grid-template-columns: 130px 1fr; gap: 5px 12px;
     margin: 14px 0; }
dt { color: #5C6B7E; font-size: 12.5px; padding-top: 1px; }
.acts-row { display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0; }
.act { font: inherit; border-radius: 7px; padding: 6px 14px; cursor: pointer;
       border: 1px solid transparent; }
.act.go { background: #1F6F6B; color: #fff; }
.act.go:hover { background: #155250; }
.act.no { background: #F0F2F5; color: #9AA7B7; border-color: #D8DFE7; }
.act .lock { font-size: 11px; }
.hint { color: #8895A7; font-size: 12px; margin: 4px 0 0; }
form.fields { display: grid; gap: 9px; max-width: 420px; margin-top: 10px; }
form.fields label { font-size: 12.5px; color: #47566A; }
form.fields input { font: inherit; padding: 6px 9px; border: 1px solid #C9D3DE;
                    border-radius: 6px; width: 100%; }
.rules { max-width: 860px; }
.rule { background: #fff; border-radius: 8px; padding: 10px 14px;
        margin-bottom: 9px; border-left: 4px solid #3A7D44;
        box-shadow: 0 1px 2px rgba(31,42,58,.08); }
.rule.deny { border-left-color: #B4552D; }
.rule .id { font-family: ui-monospace, Menlo, Consolas, monospace;
            font-weight: 700; font-size: 13px; }
.rule .eff { font-size: 11px; border-radius: 4px; padding: 1px 7px;
             color: #fff; margin-left: 7px; }
.rule .when { font-family: ui-monospace, Menlo, Consolas, monospace;
              font-size: 12px; color: #47566A; background: #F4F6F8;
              border-radius: 5px; padding: 5px 9px; margin-top: 6px;
              white-space: pre-wrap; }
.rule .desc { color: #5C6B7E; font-size: 12.5px; margin-top: 5px; }
.sect { font-size: 13px; text-transform: uppercase; letter-spacing: .05em;
        color: #47566A; margin: 20px 0 8px; }
table.lc { border-collapse: collapse; background: #fff; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 2px rgba(31,42,58,.08); }
table.lc td, table.lc th { padding: 6px 14px; border-bottom: 1px solid #ECF0F4;
                           font-size: 13px; text-align: left; }
table.lc th { background: #F4F6F8; color: #47566A; font-size: 12px; }
.newbtn { background: #1F6F6B; color: #fff; border: none; }
"""


def make_handler(rb, conn, clock=None, mutable_clock=False):
    clock = clock if clock is not None else {}
    Base = server_mod.make_handler(rb, conn, clock, mutable_clock)
    plural = rb.entity + "s"
    route_item = re.compile(r"^/ui/items/(\d+)$")
    route_act = re.compile(r"^/ui/items/(\d+)/(act|edit)$")
    state_color = {s: PALETTE[i % len(PALETTE)]
                   for i, s in enumerate(rb.states)}
    rules_by_id = {r.id: r for r in rb.rules}
    rules_by_id[rb_mod.DEFAULT_DENY.id] = rb_mod.DEFAULT_DENY

    def esc(v):
        return html.escape(str(v), quote=True)

    def pretty(v):
        """Display form of states/fields/actions. Rule ids and condition
        sources are NEVER prettified — they are the shared vocabulary."""
        return html.escape(str(v).replace("_", " "), quote=True)

    class Handler(Base):

        # -- plumbing ---------------------------------------------------------
        def persona(self):
            cookie = cookies_mod.SimpleCookie(self.headers.get("Cookie") or "")
            name = cookie["persona"].value if "persona" in cookie else ""
            if name:
                row = store.get_user(conn, name)
                if row is not None:
                    return features_mod.Actor(
                        row["name"], row["role"], bool(row["active"]),
                        {f: row[f] for f in rb.actor_fields})
            return features_mod.ANONYMOUS

        def send_html(self, body, extra_headers=()):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for k, v in extra_headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def redirect(self, path, set_cookie=None):
            self.send_response(303)
            self.send_header("Location", path)
            if set_cookie:
                self.send_header("Set-Cookie", f"persona={set_cookie}; Path=/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def form_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            q = urllib.parse.parse_qs(self.rfile.read(n).decode())
            return {k: v[0] for k, v in q.items()}

        def page(self, actor, content, banner=""):
            who = esc(actor.name)
            attrs = " · ".join(f"{esc(v)}" for v in actor.attrs.values() if v)
            persona_desc = f"{who} — {esc(actor.role)}" + (f" · {attrs}" if attrs else "")
            options = ['<option value="">anonymous</option>']
            for u in store.list_users(conn):
                sel = " selected" if u["name"] == actor.name else ""
                extra = " ".join(esc(u[f]) for f in rb.actor_fields if u[f])
                options.append(f'<option value="{esc(u["name"])}"{sel}>'
                               f'{esc(u["name"])} ({esc(u["role"])}'
                               f'{" · " + extra if extra else ""})</option>')
            return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{esc(rb.entity)} board</title><style>{CSS}</style></head><body>
<header>
  <div class="brand">{esc(plural)}<span>.app</span></div>
  <nav><a href="/ui">board</a> <a href="/ui/new">+ new {esc(rb.entity)}</a>
       <a href="/ui/rules">the rules</a></nav>
  <form method="post" action="/ui/persona">
    <span class="persona">{persona_desc}</span>
    <select name="persona">{''.join(options)}</select>
    <button>switch</button>
  </form>
</header>
<main>{banner}{content}</main></body></html>"""

        def banner_html(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "denied" in q:
                rid = q["denied"][0]
                rule = rules_by_id.get(rid)
                why = esc(rule.description) if rule else ""
                return (f'<div class="banner deny"><b>403</b> — refused by rule '
                        f'<code>{esc(rid)}</code><span class="why">{why}</span></div>')
            if "illegal" in q:
                return (f'<div class="banner deny"><b>400</b> — the lifecycle has no '
                        f'<code>{esc(q["illegal"][0])}</code> from this state</div>')
            if "ok" in q:
                return (f'<div class="banner ok">done: <code>{esc(q["ok"][0])}'
                        f'</code> succeeded</div>')
            return ""

        def decide(self, actor, action, row, new_fields=None):
            return server_mod.evaluate(rb, actor, action, row,
                                       clock.get("today"), new_fields)

        def item_actions(self, actor, row):
            """Every structurally-legal action on this item, with its verdict."""
            acts = []
            for action in rb.actions:
                if not rb.lifecycle_legal(action, row["state"]):
                    continue
                if action == "read":
                    continue
                _, verdict, _ = self.decide(actor, action, row)
                acts.append((action, verdict))
            return acts

        # -- views --------------------------------------------------------------
        def card_html(self, actor, row):
            first = rb.fields[0] if rb.fields else None
            title = esc(row[first]) if first and row[first] else f"#{row['id']}"
            meta = [f"#{row['id']} · {esc(row['author'])}"]
            for f in rb.fields[1:]:
                if row[f]:
                    meta.append(f"{pretty(f)}: {esc(row[f])}")
            chips = []
            for action, verdict in self.item_actions(actor, row):
                if verdict.effect == "allow":
                    chips.append(
                        f'<form method="post" action="/ui/items/{row["id"]}/act" '
                        f'style="display:inline"><input type="hidden" name="action" '
                        f'value="{esc(action)}"><button class="chip go">'
                        f'{pretty(action)}</button></form>')
            color = state_color.get(row["state"], "#5C6B7E")
            return (f'<div class="card" style="border-top-color:{color}">'
                    f'<div class="t"><a href="/ui/items/{row["id"]}">{title}</a></div>'
                    f'<div class="m">{" · ".join(meta)}</div>'
                    + (f'<div class="acts">{"".join(chips)}</div>' if chips else "")
                    + '</div>')

        def board(self, actor):
            visible = [r for r in store.list_items(conn)
                       if (lambda v: v is not None and v.effect == "allow")(
                           self.decide(actor, "read", r)[1])]
            cols = []
            for s in rb.states:
                rows = [r for r in visible if r["state"] == s]
                cards = "".join(self.card_html(actor, r) for r in rows)
                cols.append(
                    f'<div class="col"><h2><span class="dot" style="background:'
                    f'{state_color[s]}"></span>{pretty(s)}<span class="n">'
                    f'{len(rows)}</span></h2>{cards}</div>')
            return self.page(actor, f'<div class="board">{"".join(cols)}</div>',
                             self.banner_html())

        def detail(self, actor, row):
            first = rb.fields[0] if rb.fields else None
            title = esc(row[first]) if first and row[first] else f"#{row['id']}"
            color = state_color.get(row["state"], "#5C6B7E")
            dl = [f"<dt>author</dt><dd>{esc(row['author'])}</dd>"]
            for f in rb.fields:
                dl.append(f"<dt>{pretty(f)}</dt><dd>{esc(row[f]) or '—'}</dd>")
            buttons = []
            for action, verdict in self.item_actions(actor, row):
                if action == "edit":
                    continue  # the form below is the edit surface
                if verdict.effect == "allow":
                    buttons.append(
                        f'<form method="post" action="/ui/items/{row["id"]}/act" '
                        f'style="display:inline"><input type="hidden" name="action" '
                        f'value="{esc(action)}"><button class="act go">'
                        f'{pretty(action)}</button></form>')
                else:
                    tip = f"refused by {verdict.id}: {verdict.description}"
                    buttons.append(
                        f'<form method="post" action="/ui/items/{row["id"]}/act" '
                        f'style="display:inline"><input type="hidden" name="action" '
                        f'value="{esc(action)}"><button class="act no" '
                        f'title="{esc(tip)}"><span class="lock">🔒</span> '
                        f'{pretty(action)} <span class="lock">({esc(verdict.id)})'
                        f'</span></button></form>')
            inputs = []
            for f in rb.fields:
                typ = "date" if "date" in f else "text"
                inputs.append(f'<label>{pretty(f)}<input name="{esc(f)}" type="{typ}" '
                              f'value="{esc(row[f])}"></label>')
            _, edit_verdict, _ = self.decide(actor, "edit", row)
            edit_hint = ""
            if edit_verdict is None or edit_verdict.effect == "deny":
                rid = edit_verdict.id if edit_verdict else "the lifecycle"
                edit_hint = (f'<p class="hint">🔒 editing is refused right now '
                             f'by <b>{esc(rid)}</b> — saving will show the '
                             f'refusal.</p>')
            content = f"""<div class="detail">
<h1>{title}</h1>
<span class="state-badge" style="background:{color}">{pretty(row['state'])}</span>
<dl>{''.join(dl)}</dl>
<div class="acts-row">{''.join(buttons)}</div>
<p class="hint">Greyed actions name the rule that refuses them — same
vocabulary as the analyzer and the 403s. They stay clickable: the UI only
reflects the decision function, it never enforces.</p>
{edit_hint}<form class="fields" method="post" action="/ui/items/{row['id']}/edit">
{''.join(inputs)}<button class="act go" style="justify-self:start">save edits</button>
</form>
<p style="margin-top:12px"><a href="/ui">← back to board</a></p></div>"""
            return self.page(actor, content, self.banner_html())

        def new_form(self, actor):
            t = rb.creating_transition()
            inputs = []
            for f in rb.fields:
                typ = "date" if "date" in f else "text"
                inputs.append(f'<label>{pretty(f)}<input name="{esc(f)}" type="{typ}">'
                              f'</label>')
            content = f"""<div class="detail"><h1>new {esc(rb.entity)}</h1>
<form class="fields" method="post" action="/ui/new">{''.join(inputs)}
<button class="act go" style="justify-self:start">{pretty(t.action)}</button></form>
<p style="margin-top:12px"><a href="/ui">← back to board</a></p></div>"""
            return self.page(actor, content, self.banner_html())

        def rules_page(self, actor):
            lc = ["<table class='lc'><tr><th>action</th><th>from</th><th>to</th></tr>"]
            for t in rb.transitions:
                lc.append(f"<tr><td><code>{esc(t.action)}</code></td>"
                          f"<td>{esc(t.source)}</td><td>{esc(t.target)}</td></tr>")
            lc.append("</table>")
            parts = [f'<div class="rules"><p class="hint">This page renders '
                     f'rules.yaml — the program. The board, the buttons, the '
                     f'403s and the analyzer all follow from it.</p>',
                     '<div class="sect">lifecycle</div>', "".join(lc),
                     '<div class="sect">rules — deny overrides allow; '
                     'silence means deny</div>']
            for r in rb.rules:
                eff_color = "#3A7D44" if r.effect == "allow" else "#B4552D"
                parts.append(
                    f'<div class="rule {r.effect}"><span class="id">{esc(r.id)}'
                    f'</span><span class="eff" style="background:{eff_color}">'
                    f'{esc(r.effect)}</span>'
                    f'<div class="when">when: {esc(r.when.source)}</div>'
                    f'<div class="desc">{esc(r.description)}</div></div>')
            if rb.projections:
                parts.append('<div class="sect">projections — how facts enter '
                             'the vocabulary</div>')
                for p in rb.projections:
                    src = (f"actor.{p.actor_attr} == resource.{p.field}"
                           if p.kind == "actor_matches_field"
                           else f"resource.{p.field} < today")
                    parts.append(f'<div class="rule"><span class="id">'
                                 f'{esc(p.name)}</span>'
                                 f'<div class="when">{esc(src)}</div></div>')
            if rb.assumptions:
                parts.append('<div class="sect">assumptions — reviewed, '
                             'trusted by the analyzer</div>')
                for a in rb.assumptions:
                    parts.append(f'<div class="rule"><span class="id">{esc(a.id)}'
                                 f'</span><div class="when">{esc(a.holds.source)}'
                                 f'</div><div class="desc">{esc(a.description)}'
                                 f'</div></div>')
            parts.append("</div>")
            return self.page(actor, "".join(parts))

        # -- routing ------------------------------------------------------------
        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if not path.startswith("/ui"):
                return super().do_GET()
            actor = self.persona()
            if path in ("/ui", "/ui/"):
                return self.send_html(self.board(actor))
            if path == "/ui/new":
                return self.send_html(self.new_form(actor))
            if path == "/ui/rules":
                return self.send_html(self.rules_page(actor))
            m = route_item.match(path)
            if m:
                row = store.get_item(conn, int(m.group(1)))
                if row is None:
                    return self.redirect("/ui")
                _, verdict, _ = self.decide(actor, "read", row)
                if verdict is None or verdict.effect == "deny":
                    rid = verdict.id if verdict else "default_deny"
                    return self.redirect(f"/ui?denied={urllib.parse.quote(rid)}")
                return self.send_html(self.detail(actor, row))
            return self.redirect("/ui")

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if not path.startswith("/ui"):
                return super().do_POST()
            form = self.form_body()
            if path == "/ui/persona":
                return self.redirect("/ui", set_cookie=form.get("persona", ""))
            actor = self.persona()
            if path == "/ui/new":
                t = rb.creating_transition()
                fields = {f: str(form.get(f, "")) for f in rb.fields}
                status, verdict, _ = self.decide(actor, t.action, None, fields)
                if verdict is not None and verdict.effect == "allow":
                    item_id = store.create_item(conn, rb, actor.name, t.target, fields)
                    return self.redirect(f"/ui/items/{item_id}?ok={t.action}")
                rid = verdict.id if verdict else t.action
                return self.redirect(f"/ui/new?denied={urllib.parse.quote(rid)}")
            m = route_act.match(path)
            if not m:
                return self.redirect("/ui")
            row = store.get_item(conn, int(m.group(1)))
            if row is None:
                return self.redirect("/ui")
            back = f"/ui/items/{row['id']}"
            if m.group(2) == "edit":
                status, verdict, _ = self.decide(actor, "edit", row)
                if verdict is not None and verdict.effect == "allow":
                    store.update_item(conn, rb, row["id"],
                                      {f: str(v) for f, v in form.items()
                                       if f in rb.fields})
                    return self.redirect(f"{back}?ok=edit")
                rid = verdict.id if verdict else "edit"
                return self.redirect(f"{back}?denied={urllib.parse.quote(rid)}")
            action = form.get("action", "")
            if action not in rb.actions:
                return self.redirect(back)
            status, verdict, _ = self.decide(actor, action, row)
            if status == "illegal":
                return self.redirect(f"{back}?illegal={urllib.parse.quote(action)}")
            if verdict.effect == "deny":
                return self.redirect(f"{back}?denied={urllib.parse.quote(verdict.id)}")
            if action == "delete":
                store.delete_item(conn, row["id"])
                return self.redirect("/ui?ok=delete")
            target = rb.transition_for(action, row["state"]).target
            store.update_item(conn, rb, row["id"], {"state": target})
            return self.redirect(f"{back}?ok={urllib.parse.quote(action)}")

    return Handler
