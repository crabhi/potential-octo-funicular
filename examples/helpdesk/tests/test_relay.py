"""Relay tests, at all three layers of the architecture:

  1. the MODEL: exhaustive two-backend agreement over every situation —
     the analyzer reasons about exactly what the kernel enforces;
  2. the KERNEL: the boundary itself — typed refusals by name, the
     two-phase edit decision, visibility as the read rule;
  3. the APP over HTTP: the hand-written htmx UI cannot leak or grant
     anything — including forged requests for buttons it never rendered —
     and the boundary lint holds app.py to `engine.kernel` only.
"""

import http.client
import pathlib
import sys
import threading

import pytest
import z3

HERE = pathlib.Path(__file__).resolve().parents[1]
ENGINE_ROOT = HERE.parent / "rule-driven-cms"
sys.path.insert(0, str(ENGINE_ROOT))
sys.path.insert(0, str(HERE))

from analysis.analyze import SymbolTable  # noqa: E402
from analysis import boundary  # noqa: E402
from engine import kernel, rulebase  # noqa: E402

import app as relay  # noqa: E402

RULES = HERE / "rulesets" / "helpdesk"
RB = rulebase.load(RULES / "rules.yaml")


# --- 1. the model: exhaustive backend agreement --------------------------------

def test_backends_agree_on_every_situation():
    sym = SymbolTable(RB.vocabulary)
    conds = [r.when for r in RB.rules] + [a.holds for a in RB.assumptions]
    compiled = [c.to_z3(sym) for c in conds]
    n = 0
    for s in RB.all_situations():
        subst = []
        for var, const in sym.consts.items():
            if var in sym.lits:
                subst.append((const, sym.lits[var][s[var]]))
            else:
                subst.append((const, z3.BoolVal(s[var])))
        for cond, f in zip(conds, compiled):
            assert cond.evaluate(s) == z3.is_true(
                z3.simplify(z3.substitute(f, *subst))), (cond.source, s)
        n += 1
    assert n == 19200  # 5 roles x 10 actions x 6 states x 2^6


# --- 2. the kernel: the verified boundary ---------------------------------------

@pytest.fixture()
def desk(tmp_path):
    d = kernel.boot(RULES, tmp_path / "relay.db", today="2026-08-14",
                    seed=RULES / "features.yaml")
    relay.seed(d)
    return d


def by_subject(d, actor, subject):
    for r in d.visible(actor):
        if r["subject"] == subject:
            return r
    raise AssertionError(f"{actor.name} cannot see {subject!r}")


def test_org_walls_hold_at_the_kernel(desk):
    dana, omar, sam = (desk.actor(n) for n in ("dana", "omar", "sam"))
    acme_case = by_subject(desk, dana, "Login broken for SSO users")
    # cross-org read: typed, named refusal
    with pytest.raises(kernel.Denied) as e:
        desk.get(omar, acme_case["id"])
    assert e.value.rule.id == "org_walls"
    # visibility is partitioned; staff see everything
    assert {r["org"] for r in desk.visible(dana)} == {"acme"}
    assert {r["org"] for r in desk.visible(omar)} == {"zephyr"}
    assert {r["org"] for r in desk.visible(sam)} == {"acme", "zephyr"}
    assert desk.visible(desk.actor(None)) == []  # anonymous


def test_edit_is_decided_on_the_post_state_too(desk):
    dana = desk.actor("dana")
    row = by_subject(desk, dana, "Login broken for SSO users")
    with pytest.raises(kernel.Denied) as e:
        desk.edit(dana, row["id"], {"org": "zephyr"})   # tenant escape
    assert e.value.rule.id == "org_walls"
    assert desk.get(dana, row["id"])["org"] == "acme"   # nothing written


def test_sla_breach_escalates_to_the_lead(desk):
    sam, noor = desk.actor("sam"), desk.actor("noor")
    row = by_subject(desk, sam, "API 500s on bulk upload")  # due 08-16
    assert row["assignee"] == "sam" and row["state"] == "open"
    desk.set_today("2026-08-19")                       # the clock moves
    with pytest.raises(kernel.Denied) as e:
        desk.act(sam, "resolve", row["id"])
    assert e.value.rule.id == "breach_needs_lead"
    row = desk.act(noor, "resolve", row["id"])
    assert row["state"] == "resolved"
    desk.set_today("2026-08-14")


def test_containment_without_deny_rules(desk):
    postbot, quinn = desk.actor("postbot"), desk.actor("quinn")
    row = by_subject(desk, quinn, "Export CSV garbled")     # state: new
    for action in ("triage", "edit", "delete"):
        with pytest.raises(kernel.Denied) as e:
            if action == "edit":
                desk.edit(postbot, row["id"], {"severity": "low"})
            elif action == "delete":
                desk.delete(postbot, row["id"])
            else:
                desk.act(postbot, action, row["id"])
        assert e.value.rule.id == "default_deny"
    # staff never reopen; the requester's org does
    resolved = by_subject(desk, quinn, "Webhook retries misfire")
    with pytest.raises(kernel.Denied) as e:
        desk.act(quinn, "reopen", resolved["id"])
    assert e.value.rule.id == "default_deny"
    row = desk.act(desk.actor("dana"), "reopen", resolved["id"])
    assert row["state"] == "open"


def test_affordances_power_the_ui_but_grant_nothing(desk):
    quinn = desk.actor("quinn")
    row = by_subject(desk, quinn, "Login broken for SSO users")  # sam's, open
    acts = dict(desk.affordances(quinn, row))
    assert not acts["resolve"].allowed
    assert acts["resolve"].rule.id == "only_assignee_resolves"
    assert acts["wait"].allowed                     # staff may hold it


# --- 3. the app over HTTP: the UI cannot leak or grant ---------------------------

@pytest.fixture(scope="module")
def server(tmp_path_factory):
    db = tmp_path_factory.mktemp("relay") / "relay.db"
    desk, httpd = relay.build(db, 0)
    relay.seed(desk)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], desk
    httpd.shutdown()


def fetch(port, method, path, persona="", body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Cookie": f"persona={persona}"} if persona else {}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    text = r.read().decode()
    conn.close()
    return r.status, text


def test_the_list_is_the_read_rule(server):
    port, _ = server
    _, dana_page = fetch(port, "GET", "/?q=working", "dana")
    assert "Login broken for SSO users" in dana_page
    assert "API 500s on bulk upload" not in dana_page      # zephyr is invisible
    _, omar_page = fetch(port, "GET", "/?q=working", "omar")
    assert "API 500s on bulk upload" in omar_page
    assert "Login broken" not in omar_page
    _, anon_page = fetch(port, "GET", "/", "")
    assert "Login broken" not in anon_page and "API 500s" not in anon_page


def test_cross_org_detail_is_a_named_403(server):
    port, desk = server
    case = by_subject(desk, desk.actor("omar"), "API 500s on bulk upload")
    status, text = fetch(port, "GET", f"/case/{case['id']}", "dana")
    assert status == 403 and "org_walls" in text


def test_forged_requests_hit_the_kernel_not_the_ui(server):
    port, desk = server
    case = by_subject(desk, desk.actor("quinn"), "Export CSV garbled")
    # the UI renders postbot no buttons at all — forge the POST anyway
    status, text = fetch(port, "POST", f"/case/{case['id']}/act", "postbot",
                         body="action=triage")
    assert status == 403 and "default_deny" in text
    # quinn is staff but not the assignee: resolve is refused by name
    open_case = by_subject(desk, desk.actor("quinn"),
                           "Login broken for SSO users")
    status, text = fetch(port, "POST", f"/case/{open_case['id']}/act", "quinn",
                         body="action=resolve")
    assert status == 403 and "only_assignee_resolves" in text
    assert desk.get(desk.actor("quinn"), open_case["id"])["state"] == "open"
    # the tenant-escape edit, forged over HTTP: refused, nothing written
    status, text = fetch(port, "POST", f"/case/{open_case['id']}/edit", "dana",
                         body="org=zephyr")
    assert status == 403 and "org_walls" in text
    assert desk.get(desk.actor("dana"), open_case["id"])["org"] == "acme"


def test_allowed_flow_works_end_to_end(server):
    port, desk = server
    # priya opens a case from the form; it lands in her org's inbox
    status, text = fetch(port, "POST", "/case", "priya",
                         body="subject=Search+index+lag&severity=med&org=acme"
                              "&sla_due=2026-09-05")
    assert status == 200 and "case" in text and "Search index lag" in text
    row = by_subject(desk, desk.actor("priya"), "Search index lag")
    assert row["state"] == "new" and row["author"] == "priya"
    # a subjectless case is refused by name at the form
    status, text = fetch(port, "POST", "/case", "priya",
                         body="severity=low&org=acme")
    assert status == 403 and "case_needs_subject" in text


# --- the boundary lint holds, both directions -------------------------------------

def test_boundary_lint_passes_on_the_app():
    findings, n = boundary.scan([HERE / "app.py", HERE / "screenshots.py"])
    assert findings == [] and n >= 1


def test_boundary_lint_catches_the_bypass_variant():
    findings, _ = boundary.scan([HERE / "bypass_variant"])
    assert len(findings) >= 2
    assert any("sqlite3" in msg for _, _, msg in findings)
    assert any("engine.store" in msg for _, _, msg in findings)
