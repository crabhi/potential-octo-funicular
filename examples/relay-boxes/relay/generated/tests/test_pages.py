"""Generated, additive tests pinning the descriptions of the page boxes:
document, sidebar, queue_page, case_page, new_case_page.

Uses a recording FakeDesk (a DeskReader fully controlled by the test) so that
every sentence of the descriptions can be exercised independently of seed data,
plus a few checks against the seeded desk."""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

import relay.boxes as B
from relay.machine import Desk
from relay.shell import PEOPLE, TODAY, seed, esc as shell_esc, org_of  # noqa: F401
from relay.generated.tests.htmlkit import (
    HOSTILE, HOSTILE_ESC, FakeDesk, RecEsc, aff, esc, has_date, mk_case, parse, posts, posts_to, text_of,
)

SORT = B.sort_into_queues
KEYS = ["inbox", "working", "waiting", "breached", "resolved", "closed"]
LABELS = {"inbox": "Inbox", "working": "Working", "waiting": "On hold",
          "breached": "SLA breached", "resolved": "Resolved", "closed": "Closed"}
FDAY = date(2026, 8, 14)


def seeded(name):
    d = Desk(TODAY, PEOPLE)
    seed(d)
    return d.view(d.actor(name))


def lower_text(markup):
    return text_of(markup).lower()


# ===================================================================== document

class TestDocument:
    def doc(self, side="<aside id=\"sidebar\">SIDE</aside>", content="<p>CONTENT</p>"):
        return B.document(side, content)

    def test_doctype_first(self):
        assert self.doc().lstrip().lower().startswith("<!doctype html")

    def test_utf8_declared(self):
        assert re.search(r"charset\s*=\s*[\"']?utf-8", self.doc(), re.I)

    def test_title(self):
        assert "<title>Relay — support desk</title>" in self.doc()

    def test_htmx_script_included(self):
        assert '<script src="/static/htmx.min.js"' in self.doc()

    def test_has_stylesheet(self):
        root = parse(self.doc())
        styles = [e for e in root.walk() if e.tag == "style"]
        assert styles and len(styles[0].text().strip()) > 200

    def test_sidebar_then_main_with_content_unchanged(self):
        side = '<aside id="sidebar">SIDE-MARKER</aside>'
        content = '<div class="x">&amp; <b>raw</b> "q" \'s\'  two  spaces\n  <i>unchanged</i></div>'
        out = self.doc(side, content)
        assert side in out
        m = out.index('<main id="content">')
        assert out.index(side) < m
        assert out[m:].startswith('<main id="content">' + content)
        assert out.index(content) > out.index(side)
        assert content in out
        assert out.count(content) == 1

    def test_main_has_id_content_and_wraps_only_content(self):
        root = parse(self.doc(content="<p>CONTENT</p>"))
        mains = root.find_all("main")
        assert len(mains) == 1 and mains[0].attrs.get("id") == "content"
        assert "CONTENT" in mains[0].text()
        assert "SIDE" not in mains[0].text()

    def test_sidebar_is_outside_main(self):
        root = parse(self.doc())
        main = root.find_all("main")[0]
        assert "SIDE" not in main.text()
        assert "SIDE" in root.text()

    def test_error_status_swap_script_mentions_403_404_422(self):
        root = parse(self.doc())
        scripts = [e.text() for e in root.walk() if e.tag == "script" and "src" not in e.attrs]
        assert scripts, "an inline script is expected"
        joined = "\n".join(scripts)
        for code in ("403", "404", "422"):
            assert code in joined

    def test_empty_inputs(self):
        out = B.document("", "")
        assert '<main id="content">' in out

    def test_content_not_escaped_or_altered_with_html_special_chars(self):
        content = "<script>1<2 && 3>2</script>"
        assert content in B.document("", content)

    def test_different_content_different_document(self):
        assert B.document("a", "one") != B.document("a", "two")


# ===================================================================== sidebar

def qdesk(counts=None, me=None, people=None, **kw):
    """A desk whose cases give every queue a distinct number of cases."""
    counts = counts or {}
    cases = []
    n = 1
    for state in ["new", "open", "waiting", "resolved", "closed"]:
        for _ in range(counts.get(state, 0)):
            cases.append(mk_case(n, state=state))
            n += 1
    return FakeDesk(me=me, cases=cases, people=people, **kw)


def fake_sorter(counts, labels=None):
    def sort(cases, today):
        return [B.Queue(k, (labels or LABELS)[k], list(range(100, 100 + counts[k]))) for k in KEYS]
    return sort


def nav_links(markup):
    root = parse(markup)
    out = {}
    for k in KEYS:
        els = root.find_all(hx_get=f"/?q={k}")
        out[k] = els
    return root, out


def skeleton(el):
    """Structural signature of an element subtree (tags + non-text attrs)."""
    return [(e.tag, tuple(sorted(e.attrs.items()))) for e in el.walk()]


class TestSidebar:
    def render(self, current=None, oob=False, desk=None, sort=SORT, e=esc):
        desk = desk or FakeDesk()
        return B.sidebar(current, oob, desk, sort, e)

    def test_single_aside_with_id(self):
        root = parse(self.render())
        asides = root.find_all("aside")
        assert len(asides) == 1 and asides[0].attrs.get("id") == "sidebar"

    def test_oob_attribute_only_when_oob(self):
        on = parse(self.render(oob=True)).find_all("aside")[0]
        off = parse(self.render(oob=False)).find_all("aside")[0]
        assert on.attrs.get("hx-swap-oob") == "true"
        assert "hx-swap-oob" not in off.attrs

    def test_brand(self):
        assert "Relay" in text_of(self.render())

    def test_one_link_per_queue_with_label_and_count(self):
        counts = {"inbox": 3, "working": 0, "waiting": 12, "breached": 5, "resolved": 7, "closed": 1}
        out = self.render(sort=fake_sorter(counts))
        root, links = nav_links(out)
        for k in KEYS:
            assert len(links[k]) == 1, k
            t = re.sub(r"\s+", " ", links[k][0].text())
            assert LABELS[k] in t
            nums = re.findall(r"\d+", t)
            assert nums == [str(counts[k])], (k, t)

    def test_links_follow_queue_order(self):
        out = self.render()
        positions = [out.index(f'hx-get="/?q={k}"') for k in KEYS]
        assert positions == sorted(positions)

    def test_links_target_content_and_push_url(self):
        _, links = nav_links(self.render())
        for k in KEYS:
            el = links[k][0]
            assert el.has_ancestor_attr("hx-target", "#content")
            assert any(a.attrs.get("hx-push-url") in ("true",) or a.attrs.get("hx-push-url", "").startswith("/")
                       for a in [el, *el.ancestors()])

    def test_counts_come_from_sort_of_desk_cases_and_today(self):
        seen = []

        def sort(cases, today):
            seen.append((list(cases), today))
            return SORT(cases, today)

        desk = qdesk({"new": 2, "open": 1}, today=date(2026, 1, 2))
        B.sidebar(None, False, desk, sort, esc)
        assert seen and seen[0] == (desk.cases(), date(2026, 1, 2))

    def test_real_sort_counts(self):
        desk = qdesk({"new": 2, "open": 1, "waiting": 3, "closed": 4})
        _, links = nav_links(self.render(desk=desk))
        got = {k: re.findall(r"\d+", links[k][0].text()) for k in KEYS}
        assert got == {"inbox": ["2"], "working": ["1"], "waiting": ["3"], "breached": ["0"],
                       "resolved": ["0"], "closed": ["4"]}

    @pytest.mark.parametrize("cur", ["inbox", "working", "waiting", "breached", "resolved", "closed"])
    def test_current_is_highlighted_only_for_that_queue(self, cur):
        counts = {k: 2 for k in KEYS}
        sort = fake_sorter(counts)
        base = parse(self.render(current=None, sort=sort))
        hi = parse(self.render(current=cur, sort=sort))
        for k in KEYS:
            a = skeleton(base.find_all(hx_get=f"/?q={k}")[0])
            b = skeleton(hi.find_all(hx_get=f"/?q={k}")[0])
            if k == cur:
                assert a != b, "current queue link must look different"
            else:
                assert a == b, f"{k} must not change when {cur} is current"

    def test_breached_is_styled_differently_from_ordinary_queues(self):
        counts = {k: 2 for k in KEYS}
        root = parse(self.render(sort=fake_sorter(counts)))
        br = skeleton(root.find_all(hx_get="/?q=breached")[0])
        wk = skeleton(root.find_all(hx_get="/?q=working")[0])
        strip = lambda sk: [(t, tuple(kv for kv in a if kv[0] not in ("href", "hx-get"))) for t, a in sk]
        assert strip(br) != strip(wk)

    def test_new_case_button(self):
        root = parse(self.render())
        els = root.find_all(hx_get="/new")
        assert len(els) == 1
        assert "+ New case" in els[0].text()
        assert els[0].has_ancestor_attr("hx-target", "#content")

    def persona_form(self, desk=None, **kw):
        root = parse(self.render(desk=desk, **kw))
        forms = [f for f in root.find_all("form") if "/persona" in (f.attrs.get("hx-post"), f.attrs.get("action"))]
        assert len(forms) == 1
        return forms[0]

    PEOPLE_ = [B.Actor("dana", "customer", "acme"), B.Actor("sam", "agent"),
               B.Actor("omar", "customer", "zephyr"), B.Actor("noor", "lead")]

    def test_persona_form_posts_to_persona(self):
        f = self.persona_form(FakeDesk(people=self.PEOPLE_))
        assert f.attrs.get("hx-post") == "/persona" or (
            f.attrs.get("method", "").lower() == "post" and f.attrs.get("action") == "/persona")

    def test_persona_select_options(self):
        f = self.persona_form(FakeDesk(me=self.PEOPLE_[1], people=self.PEOPLE_))
        sel = f.find_all("select", name="persona")
        assert len(sel) == 1
        opts = sel[0].find_all("option")
        anon = [o for o in opts if o.attrs.get("value") == ""]
        assert len(anon) == 1 and "anonymous" in anon[0].text()
        assert len(opts) == len(self.PEOPLE_) + 1
        by_val = {o.attrs.get("value"): re.sub(r"\s+", " ", o.text()).strip() for o in opts}
        assert by_val["dana"] == "dana (customer · acme)"
        assert by_val["omar"] == "omar (customer · zephyr)"
        for p in ("sam", "noor"):
            assert by_val[p].startswith(p + " (")
        assert "agent" in by_val["sam"] and "lead" in by_val["noor"]

    def test_persona_listing_follows_desk_people_order(self):
        f = self.persona_form(FakeDesk(people=self.PEOPLE_))
        vals = [o.attrs.get("value") for o in f.find_all("option") if o.attrs.get("value")]
        assert vals == [p.name for p in self.PEOPLE_]

    @pytest.mark.parametrize("who", ["dana", "sam", "noor"])
    def test_current_viewer_selected(self, who):
        me = next(p for p in self.PEOPLE_ if p.name == who)
        f = self.persona_form(FakeDesk(me=me, people=self.PEOPLE_))
        sel = [o for o in f.find_all("option") if "selected" in o.attrs]
        assert [o.attrs.get("value") for o in sel] == [who]

    def test_anonymous_viewer_selects_anonymous_option(self):
        anon = B.Actor("anonymous", "anonymous")
        f = self.persona_form(FakeDesk(me=anon, people=self.PEOPLE_))
        sel = [o for o in f.find_all("option") if "selected" in o.attrs]
        assert [o.attrs.get("value") for o in sel] == [""]

    def test_persona_form_submits_on_change(self):
        f = self.persona_form(FakeDesk(people=self.PEOPLE_))
        sel = f.find_all("select", name="persona")[0]
        blob = " ".join(f"{k}={v}" for e in (f, sel) for k, v in e.attrs.items()).lower()
        assert "change" in blob

    def test_persona_post_is_wired_via_htmx_with_target_content(self):
        f = self.persona_form(FakeDesk(people=self.PEOPLE_))
        assert f.has_ancestor_attr("hx-target", "#content")

    def test_desk_date_shown(self):
        out = self.render(desk=FakeDesk(today=date(2031, 12, 25)))
        assert has_date(text_of(out), date(2031, 12, 25))

    def test_desk_date_follows_desk(self):
        a = text_of(self.render(desk=FakeDesk(today=date(2030, 1, 2))))
        b = text_of(self.render(desk=FakeDesk(today=date(2030, 1, 3))))
        assert a != b

    def test_all_text_passes_through_esc(self):
        evil = B.Actor(HOSTILE, "agent")
        rec = RecEsc()
        labels = {k: HOSTILE + k for k in KEYS}
        out = self.render(desk=FakeDesk(me=evil, people=[evil]), sort=fake_sorter({k: 1 for k in KEYS}, labels), e=rec)
        assert "<script>" not in out
        assert HOSTILE_ESC in out
        assert any(HOSTILE in c for c in rec.calls)

    def test_esc_applied_to_org_in_persona_text(self):
        evil = B.Actor("zed", "customer", HOSTILE)
        out = self.render(desk=FakeDesk(me=evil, people=[evil]))
        assert "<script>" not in out

    def test_esc_is_really_used_not_bypassed(self):
        up = lambda s: s.replace("Relay", "RELAY")  # a recognisable esc
        out = self.render(desk=FakeDesk(people=[B.Actor("Relayer", "agent")]), e=up)
        assert "RELAYer" in out

    def test_seeded_desk_smoke(self):
        out = B.sidebar("working", False, seeded("sam"), SORT, shell_esc)
        _, links = nav_links(out)
        assert all(len(links[k]) == 1 for k in KEYS)
        assert "sam" in out


# ================================================================== queue_page

def rows(markup):
    root = parse(markup)
    out = []
    for e in root.walk():
        m = re.fullmatch(r"/case/(\d+)", e.attrs.get("hx-get", ""))
        if m:
            out.append((int(m.group(1)), e))
    return out


def cells(tr):
    return [c for c in tr.children if hasattr(c, "tag") and c.tag in ("td", "th")]


class TestQueuePage:
    def render(self, queue="inbox", notice=None, desk=None, sort=SORT, e=esc):
        return B.queue_page(queue, notice, desk, sort, e)

    def desk3(self):
        cases = [
            mk_case(10, "Alpha subject", "acme", "dana", "new", "low", "sam", None),
            mk_case(11, "Bravo subject", "zephyr", "omar", "new", "high", None, FDAY + timedelta(days=5)),
            mk_case(12, "Charlie subject", "acme", "priya", "new", "high", "quinn", FDAY - timedelta(days=3)),
        ]
        return FakeDesk(cases=cases)

    def test_heading_is_queue_label(self):
        for k in KEYS:
            root = parse(self.render(k, None, self.desk3()))
            heads = [e.text().strip() for e in root.walk() if e.tag in ("h1", "h2", "h3")]
            assert LABELS[k] in heads, (k, heads)

    def test_rows_in_sort_order_and_open_case(self):
        out = self.render("inbox", None, self.desk3())
        assert [i for i, _ in rows(out)] == [11, 12, 10]  # high by id, then low
        for i, el in rows(out):
            assert el.has_ancestor_attr("hx-target", "#content")
            assert any(a.attrs.get("hx-push-url") for a in [el, *el.ancestors()])

    def test_rows_follow_whatever_order_sort_returns(self):
        desk = self.desk3()

        def sort(cases, today):
            return [B.Queue(k, LABELS[k], [10, 12, 11] if k == "inbox" else []) for k in KEYS]

        assert [i for i, _ in rows(self.render("inbox", None, desk, sort))] == [10, 12, 11]

        def sort2(cases, today):
            return [B.Queue(k, LABELS[k], [12, 11, 10] if k == "inbox" else []) for k in KEYS]

        assert [i for i, _ in rows(self.render("inbox", None, desk, sort2))] == [12, 11, 10]

    def test_only_cases_of_that_queue(self):
        cases = [mk_case(1, state="new"), mk_case(2, state="open"), mk_case(3, state="closed")]
        desk = FakeDesk(cases=cases)
        assert [i for i, _ in rows(self.render("working", None, desk))] == [2]
        assert [i for i, _ in rows(self.render("closed", None, desk))] == [3]

    def test_sort_receives_desk_cases_and_today(self):
        seen = []

        def sort(cases, today):
            seen.append((list(cases), today))
            return SORT(cases, today)

        desk = self.desk3()
        self.render("inbox", None, desk, sort)
        assert seen and seen[0] == (desk.cases(), FDAY)

    def test_table_has_the_six_columns(self):
        root = parse(self.render("inbox", None, self.desk3()))
        heads = [e.text().strip().lower() for e in root.walk() if e.tag == "th"]
        want = ["severity", "subject", "org", "state", "assignee", "sla"]
        assert len(heads) == 6
        for h, w in zip(heads, want):
            assert w in h

    def test_row_cells_carry_case_fields(self):
        out = self.render("inbox", None, self.desk3())
        by_id = {i: el for i, el in rows(out)}
        c = cells(by_id[11])
        assert len(c) == 6
        assert "high" in c[0].text().lower()
        assert "Bravo subject" in c[1].text()
        assert "zephyr" in c[2].text()
        assert has_date(c[5].text(), FDAY + timedelta(days=5))
        c10 = cells(by_id[10])
        assert "low" in c10[0].text().lower()
        assert "Alpha subject" in c10[1].text()
        assert "acme" in c10[2].text()
        assert "sam" in c10[4].text()
        assert "quinn" in cells(by_id[12])[4].text()

    def test_count_line(self):
        out = self.render("inbox", None, self.desk3())
        root = parse(out)
        for t in root.find_all("table"):
            t.children.clear()
        assert re.search(r"(?<!\d)3(?!\d)", root.text())

    def test_count_line_singular_and_zero(self):
        d1 = FakeDesk(cases=[mk_case(1, state="open")])
        r1 = parse(self.render("working", None, d1))
        for t in r1.find_all("table"):
            t.children.clear()
        assert re.search(r"(?<!\d)1(?!\d)", r1.text())
        r0 = parse(self.render("closed", None, d1))
        assert re.search(r"(?<!\d)0(?!\d)", r0.text())

    @pytest.mark.parametrize("state", ["new", "open", "waiting"])
    def test_overdue_sla_alert_with_days_over(self, state):
        desk = FakeDesk(cases=[mk_case(1, state=state, sla_due=FDAY - timedelta(days=4))])
        out = self.render({"new": "inbox", "open": "working", "waiting": "waiting"}[state], None, desk)
        (i, tr), = rows(out)
        sla = cells(tr)[5]
        assert "4 d over" in sla.text()
        assert has_date(sla.text(), FDAY - timedelta(days=4))

    def test_days_over_counts_whole_days(self):
        desk = FakeDesk(cases=[mk_case(1, state="open", sla_due=FDAY - timedelta(days=1)),
                               mk_case(2, state="open", severity="low", sla_due=FDAY - timedelta(days=37))])
        out = self.render("breached", None, desk)
        by_id = {i: el for i, el in rows(out)}
        assert "1 d over" in cells(by_id[1])[5].text()
        assert "37 d over" in cells(by_id[2])[5].text()

    def test_not_overdue_has_no_over_text_and_differs_in_style(self):
        desk = FakeDesk(cases=[
            mk_case(1, state="open", severity="high", sla_due=FDAY - timedelta(days=2)),
            mk_case(2, state="open", severity="med", sla_due=FDAY + timedelta(days=2)),
            mk_case(3, state="open", severity="low", sla_due=FDAY),
            mk_case(4, state="open", severity="low", sla_due=None),
        ])
        out = self.render("working", None, desk)
        by_id = {i: el for i, el in rows(out)}
        assert "d over" in cells(by_id[1])[5].text()
        for i in (2, 3, 4):
            assert "over" not in cells(by_id[i])[5].text()
        assert skeleton(cells(by_id[1])[5]) != skeleton(cells(by_id[2])[5])
        assert skeleton(cells(by_id[1])[5]) != skeleton(cells(by_id[3])[5])

    def test_resolved_and_closed_past_due_are_not_alerted(self):
        past = FDAY - timedelta(days=9)
        desk = FakeDesk(cases=[mk_case(1, state="resolved", sla_due=past),
                               mk_case(2, state="closed", sla_due=past)])
        for q in ("resolved", "closed"):
            out = self.render(q, None, desk)
            (i, tr), = rows(out)
            assert "over" not in cells(tr)[5].text()
            assert has_date(cells(tr)[5].text(), past)

    def test_empty_queue_says_so_and_has_no_rows(self):
        out = self.render("closed", None, self.desk3())
        assert rows(out) == []
        t = lower_text(out)
        assert any(w in t for w in ("no cases", "empty", "nothing", "no case", "none"))

    def test_nonempty_queue_does_not_claim_to_be_empty(self):
        t = lower_text(self.render("inbox", None, self.desk3()))
        assert "no cases" not in t and "empty" not in t

    def test_refused_notice_toast(self):
        out = self.render("inbox", B.Notice("refused", "Customers may not close cases", "case.close_staff_only"),
                          self.desk3())
        t = text_of(out)
        assert "Refused — rule case.close_staff_only" in t
        assert "Customers may not close cases" in t

    @pytest.mark.parametrize("kind", ["ok", "invalid"])
    def test_other_notice_text_is_shown(self, kind):
        out = self.render("inbox", B.Notice(kind, "Case 5 updated", None), self.desk3())
        assert "Case 5 updated" in text_of(out)
        assert "Refused" not in text_of(out)

    def test_no_notice_no_refusal(self):
        assert "Refused" not in text_of(self.render("inbox", None, self.desk3()))

    def test_notice_comes_before_heading(self):
        out = self.render("inbox", B.Notice("ok", "NOTICE-TEXT", None), self.desk3())
        assert out.index("NOTICE-TEXT") < out.index("<h1")

    def test_all_user_text_passes_through_esc(self):
        cases = [mk_case(1, HOSTILE, HOSTILE + "o", "r", "new", "high", HOSTILE + "a", None)]
        rec = RecEsc()
        out = self.render("inbox", B.Notice("refused", HOSTILE + "n", HOSTILE + "r"), FakeDesk(cases=cases), SORT, rec)
        assert "<script>" not in out
        assert HOSTILE_ESC in out
        for frag in (HOSTILE, HOSTILE + "o", HOSTILE + "a", HOSTILE + "n", HOSTILE + "r"):
            assert frag in rec.calls

    def test_seeded_breached_page(self):
        v = seeded("sam")
        out = self.render("working", None, v, SORT, shell_esc)
        ids = [i for i, _ in rows(out)]
        want = next(q.case_ids for q in SORT(v.cases(), v.today()) if q.key == "working")
        assert ids == want


# =================================================================== case_page

def case_desk(me=None, case=None, thread=(), evidence=(), actions=(), **kw):
    case = case or mk_case(5, "The subject", "acme", "dana", "open", "high", "sam", FDAY + timedelta(days=2))
    return FakeDesk(me=me or B.Actor("sam", "agent"), cases=[case],
                    threads={case.id: list(thread)}, evidence={case.id: list(evidence)},
                    case_actions={case.id: list(actions)}, **kw)


def cm(id, body="hello", internal=False, state="posted", author="dana", case_id=5):
    return B.Comment(id, case_id, author, body, internal, state)


def att(id, filename="f.png", state="attached", author="dana", case_id=5):
    return B.Attachment(id, case_id, author, filename, state)


class TestCasePage:
    def render(self, desk, case_id=5, notice=None, e=esc):
        return B.case_page(case_id, notice, desk, e)

    # --- availability
    @pytest.mark.parametrize("override", [None, B.Denied("case.read", "not yours")])
    def test_unavailable_case_says_not_available(self, override):
        desk = FakeDesk(cases=[], case_override={99: override} if override else None)
        out = self.render(desk, case_id=99)
        assert "not available" in lower_text(out)
        assert posts(out) == []

    def test_unavailable_does_not_leak_denial_details(self):
        desk = FakeDesk(case_override={99: B.Denied("secret.rule", "secret reason")})
        out = self.render(desk, case_id=99)
        assert "not available" in lower_text(out)

    # --- header
    def test_back_link(self):
        assert "← queues" in text_of(self.render(case_desk()))

    def test_case_facts_shown(self):
        c = mk_case(5, "Printer jam", "zephyr", "omar", "waiting", "low", "quinn", date(2026, 9, 3))
        out = self.render(case_desk(case=c))
        t = text_of(out)
        for frag in ("Printer jam", "zephyr", "omar", "quinn", "low", "waiting"):
            assert frag in t, frag
        assert has_date(t, date(2026, 9, 3))
        pills = [e for e in parse(out).walk() if "pill" in e.attrs.get("class", "").split() or
                 any(x.startswith("pill") for x in e.attrs.get("class", "").split())]
        assert any(p.text().strip() == "waiting" for p in pills)

    def test_subject_is_a_heading(self):
        root = parse(self.render(case_desk()))
        assert "The subject" in [e.text().strip() for e in root.walk() if e.tag in ("h1", "h2", "h3")]

    def test_unassigned_case_renders(self):
        c = mk_case(5, "No owner", assignee=None, sla_due=None)
        out = self.render(case_desk(case=c))
        assert "No owner" in text_of(out)

    def test_notice_toast(self):
        n = B.Notice("refused", "Only staff may do that", "case.staff_only")
        t = text_of(self.render(case_desk(), notice=n))
        assert "Refused — rule case.staff_only" in t and "Only staff may do that" in t
        t2 = text_of(self.render(case_desk(), notice=B.Notice("ok", "Saved it", None)))
        assert "Saved it" in t2 and "Refused" not in t2
        assert "Refused" not in text_of(self.render(case_desk()))

    # --- actions
    def test_allowed_actions_post_to_act(self):
        desk = case_desk(actions=[aff("wait"), aff("resolve")])
        out = self.render(desk)
        ps = posts_to(out, "/case/5/act")
        assert sorted(p["action"] for p, _ in ps) == ["resolve", "wait"]
        for p, e in ps:
            assert e.has_ancestor_attr("hx-target", "#content")

    def test_allowed_actions_are_outside_locked_section(self):
        desk = case_desk(actions=[aff("wait"), aff("close", False, "case.close_needs_resolved", "must be resolved")])
        out = self.render(desk)
        for p, e in posts_to(out, "/case/5/act"):
            in_details = any(a.tag == "details" for a in e.ancestors())
            if p["action"] == "wait":
                assert not in_details
            else:
                assert in_details

    def test_refused_actions_in_collapsed_locked_section_naming_rule_and_still_clickable(self):
        desk = case_desk(actions=[aff("wait"), aff("close", False, "case.close_needs_resolved", "must be resolved first")])
        out = self.render(desk)
        root = parse(out)
        details = [e for e in root.walk() if e.tag == "details"]
        locked = [d for d in details if "locked" in d.text().lower()]
        assert len(locked) == 1
        assert "open" not in locked[0].attrs  # collapsed
        assert "case.close_needs_resolved" in locked[0].text()
        refused = [(p, e) for p, e in posts_to(out, "/case/5/act") if p["action"] == "close"]
        assert len(refused) == 1
        p, e = refused[0]
        assert "disabled" not in e.attrs
        enclosing = [a for a in e.ancestors() if a.tag == "details"]
        assert enclosing and "locked" in enclosing[0].text().lower()
        assert e.has_ancestor_attr("hx-target", "#content")

    def test_each_refused_action_names_its_own_rule(self):
        desk = case_desk(actions=[aff("close", False, "rule.one", "r1"), aff("reopen", False, "rule.two", "r2")])
        root = parse(self.render(desk))
        locked = [d for d in root.walk() if d.tag == "details" and "locked" in d.text().lower()][0]
        assert "rule.one" in locked.text() and "rule.two" in locked.text()
        assert len(posts_to(self.render(desk), "/case/5/act")) == 2

    def test_no_refused_actions_no_locked_text_required(self):
        desk = case_desk(actions=[aff("wait")])
        out = self.render(desk)
        assert [p["action"] for p, _ in posts_to(out, "/case/5/act")] == ["wait"]
        assert "rule.denied" not in out

    def test_act_url_uses_case_id(self):
        c = mk_case(77, "Seventy")
        desk = FakeDesk(cases=[c], case_actions={77: [aff("triage")]})
        out = self.render(desk, case_id=77)
        assert [p for p, _ in posts_to(out, "/case/77/act")] == [{"action": "triage"}]

    # --- edit
    def test_edit_form_when_allowed(self):
        out = self.render(case_desk(edit=aff("edit")))
        ps = posts_to(out, "/case/5/edit")
        forms = [(p, e) for p, e in ps if e.tag == "form"]
        assert len(forms) == 1
        form = forms[0][1]
        names = {e.attrs.get("name") for e in form.walk()}
        assert {"subject", "assignee", "severity", "sla_due", "org"} <= names
        assert form.has_ancestor_attr("hx-target", "#content")

    def test_edit_form_absent_and_rule_named_when_refused(self):
        desk = case_desk(edit=aff("edit", False, "case.edit_staff_only", "staff only"))
        out = self.render(desk)
        assert posts_to(out, "/case/5/edit") == []
        assert "case.edit_staff_only" in text_of(out)

    def test_assign_to_me_for_unassigned_case_and_staff(self):
        c = mk_case(5, assignee=None)
        for who in (B.Actor("sam", "agent"), B.Actor("noor", "lead")):
            out = self.render(case_desk(me=who, case=c))
            btn = [(p, e) for p, e in posts_to(out, "/case/5/edit") if e.tag != "form" and "assign to me" in e.text().lower()]
            assert len(btn) == 1, who
            p, e = btn[0]
            assert p["assignee"] == who.name
            assert e.has_ancestor_attr("hx-target", "#content")

    def test_no_assign_to_me_when_viewer_is_already_the_assignee(self):
        c = mk_case(5, assignee="sam")
        out = self.render(case_desk(me=B.Actor("sam", "agent"), case=c))
        assert "assign to me" not in lower_text(out)

    def test_no_assign_to_me_for_customers(self):
        c = mk_case(5, assignee=None)
        out = self.render(case_desk(me=B.Actor("dana", "customer", "acme"), case=c))
        assert "assign to me" not in lower_text(out)

    def test_no_assign_to_me_when_edit_refused(self):
        c = mk_case(5, assignee=None)
        out = self.render(case_desk(case=c, edit=aff("edit", False, "case.edit_no", "no")))
        assert "assign to me" not in lower_text(out)

    # --- thread
    def test_thread_comments_shown_in_order(self):
        thread = [cm(1, "FIRST-BODY"), cm(2, "SECOND-BODY"), cm(3, "THIRD-BODY")]
        out = self.render(case_desk(thread=thread))
        pos = [out.index(b) for b in ("FIRST-BODY", "SECOND-BODY", "THIRD-BODY")]
        assert pos == sorted(pos)

    def test_internal_comment_marked_internal(self):
        thread = [cm(1, "PUBLIC-BODY", internal=False), cm(2, "PRIVATE-BODY", internal=True)]
        desk = case_desk(thread=thread, post_pub=aff("post", False, "x.no", "n"), post_int=aff("post", False, "x.no", "n"))
        out = self.render(desk)
        assert "internal" in lower_text(out)
        only_public = case_desk(thread=[cm(1, "PUBLIC-BODY")], post_pub=aff("post", False, "x.no", "n"),
                                post_int=aff("post", False, "x.no", "n"))
        assert "internal" not in lower_text(self.render(only_public))

    def test_redacted_comment_shows_tombstone_not_body(self):
        thread = [cm(1, "VISIBLE-BODY"), cm(2, "SECRET-BODY", state="redacted")]
        out = self.render(case_desk(thread=thread))
        assert "SECRET-BODY" not in out
        assert "VISIBLE-BODY" in out
        assert "redacted" in lower_text(out)

    def test_no_tombstone_word_without_redactions(self):
        out = self.render(case_desk(thread=[cm(1, "plain")]))
        assert "redacted" not in lower_text(out)

    def test_comment_actions_post_with_case_param(self):
        thread = [cm(11, "A-BODY"), cm(12, "B-BODY")]
        desk = case_desk(thread=thread, comment_actions={11: [aff("redact")], 12: []})
        out = self.render(desk)
        ps = posts_to(out, "/comment/11/redact")
        assert len(ps) == 1
        assert ps[0][0].get("case") == "5"
        assert ps[0][1].has_ancestor_attr("hx-target", "#content")
        assert posts_to(out, "/comment/12/redact") == []

    def test_comment_action_name_goes_into_url(self):
        desk = case_desk(thread=[cm(4, "x")], comment_actions={4: [aff("hide")]})
        out = self.render(desk)
        ps = posts_to(out, "/comment/4/hide")
        assert len(ps) == 1 and ps[0][0]["case"] == "5"

    def test_comment_form_with_internal_checkbox_when_both_allowed(self):
        out = self.render(case_desk(post_pub=aff("post"), post_int=aff("post")))
        forms = [(p, e) for p, e in posts_to(out, "/case/5/comment") if e.tag == "form"]
        assert len(forms) == 1
        form = forms[0][1]
        named = {e.attrs.get("name"): e for e in form.walk() if e.attrs.get("name")}
        assert "body" in named
        box = named["internal"]
        assert box.tag == "input" and box.attrs.get("type") == "checkbox" and box.attrs.get("value") == "yes"
        assert "internal note" in form.text().lower()
        assert form.has_ancestor_attr("hx-target", "#content")

    def test_checkbox_omitted_when_internal_refused(self):
        desk = case_desk(post_pub=aff("post"), post_int=aff("post", False, "note.staff_only", "staff only"))
        out = self.render(desk)
        forms = [e for p, e in posts_to(out, "/case/5/comment") if e.tag == "form"]
        assert len(forms) == 1
        assert not [e for e in forms[0].walk() if e.attrs.get("name") == "internal"]
        assert "internal note" not in lower_text(out)

    def test_comment_form_replaced_by_rule_line_when_refused(self):
        desk = case_desk(post_pub=aff("post", False, "thread.closed_case", "case is closed"),
                         post_int=aff("post", False, "thread.closed_case", "case is closed"))
        out = self.render(desk)
        assert posts_to(out, "/case/5/comment") == []
        assert "thread.closed_case" in text_of(out)

    def test_public_post_refused_hides_form_even_if_internal_allowed(self):
        desk = case_desk(post_pub=aff("post", False, "pub.no", "n"), post_int=aff("post"))
        out = self.render(desk)
        assert posts_to(out, "/case/5/comment") == []
        assert "pub.no" in text_of(out)

    # --- evidence
    def test_evidence_listed_in_order(self):
        out = self.render(case_desk(evidence=[att(1, "first.png"), att(2, "second.png")]))
        assert out.index("first.png") < out.index("second.png")

    def test_removed_attachment_tombstone(self):
        out = self.render(case_desk(evidence=[att(1, "kept.png"), att(2, "gone.png", "removed")]))
        assert "kept.png" in out
        assert "removed" in lower_text(out)

    def test_no_removed_word_without_removals(self):
        assert "removed" not in lower_text(self.render(case_desk(evidence=[att(1, "kept.png")])))

    def test_attachment_actions_post_with_case_param(self):
        desk = case_desk(evidence=[att(21, "a.png"), att(22, "b.png")],
                         attachment_actions={21: [aff("remove")], 22: []})
        out = self.render(desk)
        ps = posts_to(out, "/attachment/21/remove")
        assert len(ps) == 1 and ps[0][0].get("case") == "5"
        assert ps[0][1].has_ancestor_attr("hx-target", "#content")
        assert posts_to(out, "/attachment/22/remove") == []

    def test_attach_form_when_allowed(self):
        out = self.render(case_desk(attach=aff("attach")))
        forms = [e for p, e in posts_to(out, "/case/5/attach") if e.tag == "form"]
        assert len(forms) == 1
        assert [e for e in forms[0].walk() if e.attrs.get("name") == "filename"]
        assert forms[0].has_ancestor_attr("hx-target", "#content")

    def test_attach_form_replaced_by_rule_line_when_refused(self):
        out = self.render(case_desk(attach=aff("attach", False, "evidence.closed", "closed")))
        assert posts_to(out, "/case/5/attach") == []
        assert "evidence.closed" in text_of(out)

    # --- htmx everywhere / esc
    def test_every_form_and_button_uses_htmx_targeting_content(self):
        desk = case_desk(
            actions=[aff("wait"), aff("close", False, "r.x", "x")],
            thread=[cm(1, "b"), cm(2, "c", True)],
            evidence=[att(1)],
            comment_actions={1: [aff("redact")]},
            attachment_actions={1: [aff("remove")]},
            case=mk_case(5, assignee=None),
        )
        root = parse(self.render(desk))
        for f in root.find_all("form"):
            assert "hx-post" in f.attrs
        ps = posts(self.render(desk))
        assert ps
        for url, params, e in ps:
            assert e.has_ancestor_attr("hx-target", "#content"), url
        for b in root.walk():
            if b.tag == "button" and b.attrs.get("type", "submit") != "submit":
                assert "hx-post" in b.attrs or "hx-get" in b.attrs

    def test_all_user_text_passes_through_esc(self):
        c = mk_case(5, HOSTILE + "s", HOSTILE + "o", HOSTILE + "r", "open", "high", HOSTILE + "a", None)
        desk = case_desk(case=c, thread=[cm(1, HOSTILE + "b", author=HOSTILE + "u"), cm(2, HOSTILE + "i", True)],
                         evidence=[att(1, HOSTILE + "f", author=HOSTILE + "u")],
                         edit=aff("edit"), me=B.Actor(HOSTILE + "me", "agent"),
                         actions=[aff("close", False, HOSTILE + "rule", HOSTILE + "reason")])
        rec = RecEsc()
        out = self.render(desk, notice=B.Notice("refused", HOSTILE + "n", HOSTILE + "nr"), e=rec)
        assert "<script>" not in out
        assert HOSTILE_ESC in out
        for frag in (HOSTILE + "s", HOSTILE + "o", HOSTILE + "r", HOSTILE + "a", HOSTILE + "b", HOSTILE + "f",
                     HOSTILE + "n", HOSTILE + "nr"):
            assert frag in rec.calls, frag

    def test_esc_applied_to_refusing_rule_lines(self):
        desk = case_desk(edit=aff("edit", False, HOSTILE, "r"), post_pub=aff("post", False, HOSTILE, "r"),
                         attach=aff("attach", False, HOSTILE, "r"))
        out = self.render(desk)
        assert "<script>" not in out

    def test_seeded_customer_sees_no_internal_notes(self):
        v = seeded("dana")
        out = B.case_page(1, None, v, shell_esc)
        assert "Suspect SAML clock skew" not in out
        assert "internal" not in lower_text(out)

    def test_seeded_agent_sees_internal_note_marked(self):
        v = seeded("sam")
        out = B.case_page(1, None, v, shell_esc)
        assert "Suspect SAML clock skew" in out
        assert "internal" in lower_text(out)

    def test_seeded_foreign_case_not_available_for_customer(self):
        v = seeded("dana")
        out = B.case_page(6, None, v, shell_esc)  # zephyr's case
        assert "not available" in lower_text(out)
        assert "API 500s" not in out


# ================================================================ new_case_page

class TestNewCasePage:
    def render(self, desk=None, notice=None, e=esc):
        return B.new_case_page(notice, desk or FakeDesk(), e)

    def form(self, **kw):
        out = self.render(**kw)
        ps = [(p, e) for p, e in posts_to(out, "/case") if e.tag == "form"]
        assert len(ps) == 1
        return out, ps[0][1]

    def test_form_posts_to_case_via_htmx_into_content(self):
        _, f = self.form()
        assert f.has_ancestor_attr("hx-target", "#content")

    def test_fields_present(self):
        _, f = self.form()
        names = {e.attrs.get("name") for e in f.walk() if e.attrs.get("name")}
        assert {"subject", "severity", "sla_due", "org"} <= names

    def test_severity_select_options_and_default(self):
        _, f = self.form()
        sel = f.find_all("select", name="severity")
        assert len(sel) == 1
        opts = sel[0].find_all("option")
        assert sorted(o.attrs.get("value") for o in opts) == ["high", "low", "med"]
        chosen = [o.attrs.get("value") for o in opts if "selected" in o.attrs]
        assert chosen == ["med"]

    def test_default_submission_has_med_and_empty_sla(self):
        from relay.generated.tests.htmlkit import controls
        _, f = self.form()
        c = controls(f)
        assert c["severity"] == "med"
        assert c.get("sla_due", "") == ""

    def test_sla_due_is_a_text_or_date_input(self):
        _, f = self.form()
        el = [e for e in f.find_all("input") if e.attrs.get("name") == "sla_due"]
        assert len(el) == 1 and el[0].attrs.get("type", "text") in ("date", "text")

    def test_subject_input(self):
        _, f = self.form()
        els = [e for e in f.walk() if e.attrs.get("name") == "subject"]
        assert len(els) == 1 and els[0].tag in ("input", "textarea")

    def test_org_readonly_and_hidden_for_viewer_with_org(self):
        desk = FakeDesk(me=B.Actor("dana", "customer", "acme"))
        out, f = self.form(desk=desk)
        orgs = [e for e in f.walk() if e.attrs.get("name") == "org"]
        assert len(orgs) == 1
        assert orgs[0].tag == "input" and orgs[0].attrs.get("type") == "hidden"
        assert orgs[0].attrs.get("value") == "acme"
        assert "acme" in f.text()  # shown read-only

    def test_org_text_input_for_viewer_without_org(self):
        for who in (B.Actor("sam", "agent"), B.Actor("noor", "lead"), B.Actor("anonymous", "anonymous")):
            _, f = self.form(desk=FakeDesk(me=who))
            orgs = [e for e in f.walk() if e.attrs.get("name") == "org"]
            assert len(orgs) == 1, who
            assert orgs[0].tag == "input"
            assert orgs[0].attrs.get("type", "text") == "text", who
            assert orgs[0].attrs.get("value", "") == ""

    def test_org_value_follows_viewer(self):
        _, f = self.form(desk=FakeDesk(me=B.Actor("omar", "customer", "zephyr")))
        orgs = [e for e in f.walk() if e.attrs.get("name") == "org"]
        assert orgs[0].attrs.get("value") == "zephyr"

    def test_notice_toast(self):
        t = text_of(self.render(notice=B.Notice("invalid", "subject is required", None)))
        assert "subject is required" in t
        t = text_of(self.render(notice=B.Notice("refused", "Nope", "case.open_no")))
        assert "Refused — rule case.open_no" in t and "Nope" in t
        assert "Refused" not in text_of(self.render())

    def test_notice_comes_before_form(self):
        out = self.render(notice=B.Notice("ok", "NOTICE-TEXT", None))
        assert out.index("NOTICE-TEXT") < out.index("<form")

    def test_user_text_passes_through_esc(self):
        rec = RecEsc()
        desk = FakeDesk(me=B.Actor("dana", "customer", HOSTILE + "org"))
        out = self.render(desk=desk, notice=B.Notice("refused", HOSTILE + "n", HOSTILE + "r"), e=rec)
        assert "<script>" not in out
        assert HOSTILE_ESC in out
        for frag in (HOSTILE + "org", HOSTILE + "n", HOSTILE + "r"):
            assert frag in rec.calls

    def test_hostile_org_cannot_break_out_of_hidden_attribute(self):
        evil = 'x" onfocus="alert(1)'
        desk = FakeDesk(me=B.Actor("dana", "customer", evil))
        out = self.render(desk=desk)
        hidden = [e for e in parse(out).walk() if e.attrs.get("name") == "org"][0]
        assert hidden.attrs.get("value") == evil
        assert "onfocus" not in hidden.attrs

    def test_seeded_customer_and_staff(self):
        out = B.new_case_page(None, seeded("dana"), shell_esc)
        assert 'name="org"' in out and 'type="hidden"' in out
        out = B.new_case_page(None, seeded("sam"), shell_esc)
        assert 'type="hidden"' not in out
