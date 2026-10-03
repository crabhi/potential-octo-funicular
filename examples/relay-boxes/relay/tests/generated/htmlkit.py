"""Tiny HTML helpers for the generated tests: a lenient DOM, a collector of
htmx POSTs (url + effective form parameters) and a recording fake DeskReader.
Nothing here depends on the implementation."""
from __future__ import annotations

import html as _html
import json
import re
from datetime import date
from html.parser import HTMLParser

import relay.boxes as B

VOID = {"input", "br", "hr", "img", "meta", "link", "col", "wbr", "source"}


class El:
    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = {k: (v if v is not None else "") for k, v in attrs}
        self.parent = parent
        self.children = []  # El or str

    def text(self):
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return "".join(out)

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, El):
                yield from c.walk()

    def ancestors(self):
        p = self.parent
        while p is not None:
            yield p
            p = p.parent

    def find_all(self, tag=None, **attrs):
        res = []
        for e in self.walk():
            if tag is not None and e.tag != tag:
                continue
            if all(e.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items()):
                res.append(e)
        return res

    def has_ancestor_attr(self, name, value):
        return any(a.attrs.get(name) == value for a in [self, *self.ancestors()])


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = El("#root", [])
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        e = El(tag, attrs, self.cur)
        self.cur.children.append(e)
        if tag not in VOID:
            self.cur = e

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(El(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        e = self.cur
        while e is not None and e.tag != tag:
            e = e.parent
        if e is not None and e.parent is not None:
            self.cur = e.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(markup: str) -> El:
    p = _P()
    p.feed(markup)
    p.close()
    return p.root


def text_of(markup: str) -> str:
    return re.sub(r"\s+", " ", parse(markup).text()).strip()


def controls(scope: El) -> dict:
    """Named successful controls under `scope` (what a browser would submit)."""
    out = {}
    for e in scope.walk():
        name = e.attrs.get("name")
        if not name:
            continue
        if e.tag == "input":
            t = e.attrs.get("type", "text").lower()
            if t in ("checkbox", "radio"):
                if "checked" in e.attrs:
                    out[name] = e.attrs.get("value", "on")
            elif t not in ("submit", "button"):
                out[name] = e.attrs.get("value", "")
        elif e.tag == "textarea":
            out[name] = e.text()
        elif e.tag == "select":
            opts = e.find_all("option")
            chosen = [o for o in opts if "selected" in o.attrs] or opts[:1]
            if chosen:
                out[name] = chosen[0].attrs.get("value", chosen[0].text())
    return out


def posts(markup: str):
    """Every htmx POST in `markup`: list of (url, params, element)."""
    root = parse(markup)
    res = []
    for e in root.walk():
        url = e.attrs.get("hx-post")
        if url is None:
            continue
        params = {}
        form = e if e.tag == "form" else next((a for a in e.ancestors() if a.tag == "form"), None)
        if form is not None:
            params.update(controls(form))
        if e.tag in ("button", "input") and e.attrs.get("name"):
            params[e.attrs["name"]] = e.attrs.get("value", "")
        if "hx-vals" in e.attrs:
            params.update({k: str(v) for k, v in json.loads(e.attrs["hx-vals"]).items()})
        res.append((url, params, e))
    return res


def posts_to(markup, url):
    return [(p, e) for (u, p, e) in posts(markup) if u == url]


def date_forms(d: date):
    """Lenient renderings of a date: ISO, or day/month-name forms."""
    mon = d.strftime("%b")
    full = d.strftime("%B")
    return [d.isoformat(), f"{d.day} {mon} {d.year}", f"{mon} {d.day}, {d.year}",
            f"{d.day} {full} {d.year}", f"{full} {d.day}, {d.year}", f"{mon} {d.day}", f"{d.day} {mon}"]


def has_date(text: str, d: date) -> bool:
    return any(f in text for f in date_forms(d))


def esc(s: str) -> str:
    return _html.escape(s, quote=True)


class RecEsc:
    def __init__(self):
        self.calls = []

    def __call__(self, s):
        self.calls.append(s)
        return esc(s)


HOSTILE = '<script>alert("x")</script>'
HOSTILE_ESC = esc(HOSTILE)


def aff(action, allowed=True, rule=None, reason=None):
    if not allowed and rule is None:
        rule = "rule.denied"
    if not allowed and reason is None:
        reason = "not permitted"
    return B.Affordance(action, allowed, rule, reason)


class FakeDesk:
    """A DeskReader fully controlled by the test."""

    def __init__(self, me=None, cases=(), people=None, today=date(2026, 8, 14),
                 threads=None, evidence=None, case_actions=None, edit=None,
                 post_pub=None, post_int=None, attach=None,
                 comment_actions=None, attachment_actions=None, case_override=None):
        self._me = me or B.Actor("sam", "agent")
        self._cases = list(cases)
        self._people = list(people) if people is not None else [self._me]
        self._today = today
        self._threads = threads or {}
        self._evidence = evidence or {}
        self._case_actions = case_actions or {}
        self._edit = edit if edit is not None else aff("edit")
        self._post_pub = post_pub if post_pub is not None else aff("post")
        self._post_int = post_int if post_int is not None else aff("post")
        self._attach = attach if attach is not None else aff("attach")
        self._comment_actions = comment_actions or {}
        self._attachment_actions = attachment_actions or {}
        self._case_override = case_override or {}

    def me(self): return self._me
    def today(self): return self._today
    def people(self): return list(self._people)
    def cases(self): return list(self._cases)

    def case(self, case_id):
        if case_id in self._case_override:
            return self._case_override[case_id]
        for c in self._cases:
            if c.id == case_id:
                return c
        return None

    def thread(self, case_id): return list(self._threads.get(case_id, []))
    def evidence(self, case_id): return list(self._evidence.get(case_id, []))
    def case_actions(self, case_id): return list(self._case_actions.get(case_id, []))
    def may_edit(self, case_id): return self._edit
    def may_post(self, case_id, internal): return self._post_int if internal else self._post_pub
    def may_attach(self, case_id): return self._attach
    def comment_actions(self, comment_id): return list(self._comment_actions.get(comment_id, []))
    def attachment_actions(self, attachment_id): return list(self._attachment_actions.get(attachment_id, []))


def mk_case(id=1, subject="Subj", org="acme", requester="dana", state="open",
            severity="med", assignee=None, sla_due=None):
    return B.Case(id, subject, org, requester, state, severity, assignee, sla_due)
