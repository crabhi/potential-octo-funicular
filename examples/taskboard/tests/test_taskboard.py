"""Flowdeck tests: exhaustive two-backend agreement for THIS rule base
(34,560 situations — what the analyzer proves is exactly what the server
enforces), decision spot checks for the ticket sentences, and the round-2
regression (the real development bugs stay caught)."""

import pathlib
import sys

import z3

HERE = pathlib.Path(__file__).resolve().parents[1]
ENGINE_ROOT = HERE.parent / "rule-driven-cms"
sys.path.insert(0, str(ENGINE_ROOT))

from analysis.analyze import SymbolTable  # noqa: E402
from engine import features, rulebase  # noqa: E402

RS = HERE / "rulesets"
TB = rulebase.load(RS / "taskboard/rules.yaml")
ROUND2 = rulebase.load(RS / "taskboard-round2/rules.yaml")
FEATURES = RS / "taskboard/features.yaml"


def test_backends_agree_on_every_situation():
    sym = SymbolTable(TB.vocabulary)
    conds = [r.when for r in TB.rules] + [a.holds for a in TB.assumptions]
    compiled = [c.to_z3(sym) for c in conds]
    for s in TB.all_situations():
        subst = []
        for var, const in sym.consts.items():
            if var in sym.lits:
                subst.append((const, sym.lits[var][s[var]]))
            else:
                subst.append((const, z3.BoolVal(s[var])))
        for cond, f in zip(conds, compiled):
            assert cond.evaluate(s) == z3.is_true(z3.simplify(
                z3.substitute(f, *subst))), (cond.source, s)


def situation(rb=TB, role="member", name="tom", team="argo", action="read",
              state="backlog", assignee="tom", res_team="argo", **kw):
    fields = {"title": kw.get("title", "t"), "estimate": kw.get("estimate", "1d"),
              "assignee": assignee, "team": res_team,
              "due_date": kw.get("due_date", "2026-08-20")}
    return rb.situation(role, kw.get("active", True), kw.get("is_author", False),
                        action, state, fields, today=kw.get("today", "2026-08-14"),
                        actor_attrs={"name": name, "team": team})


def test_team_walls_are_absolute():
    v = TB.decide(situation(role="member", name="nadia", team="boreal"))
    assert v.effect == "deny" and v.id == "team_walls"
    v = TB.decide(situation(role="member", name="nadia", team="boreal",
                            action="create", state="none"))
    assert v.id == "team_walls"  # cannot create into another team either


def test_no_self_approval_even_for_leads():
    v = TB.decide(situation(role="lead", name="mira", assignee="mira",
                            action="approve", state="in_review"))
    assert v.effect == "deny" and v.id == "no_self_approval"


def test_staff_never_works_or_decides():
    v = TB.decide(situation(role="admin", name="ada", team="",
                            action="submit", state="in_progress", assignee="tom"))
    assert v.effect == "deny" and v.id == "only_assignee_works"
    v = TB.decide(situation(role="admin", name="ada", team="",
                            action="approve", state="in_review", assignee="tom"))
    assert v.effect == "deny" and v.id == "only_leads_decide"


def test_janitor_obeys_the_calendar():
    early = situation(role="janitor", name="dusty", team="", action="archive",
                      state="done", due_date="2026-08-20", today="2026-08-14")
    late = situation(role="janitor", name="dusty", team="", action="archive",
                     state="done", due_date="2026-08-20", today="2026-09-14")
    assert TB.decide(early).id == "janitor_waits"
    assert TB.decide(late).id == "janitor_archives"


def test_janitor_contained_without_a_scope_rule():
    v = TB.decide(situation(role="janitor", name="dusty", team="",
                            action="edit", state="in_progress"))
    assert v.effect == "deny" and v.id == "default_deny"


def test_frozen_features_pass_purely():
    for fid, result in features.run_all_pure(TB, FEATURES):
        assert result.ok, (fid, result.message)


def test_round2_draft_still_has_its_holes():
    # the S2 hole, concretely: a task assigned to "anonymous" hands
    # start to the public in the round-2 draft; the shipped rules refuse it
    hole = situation(rb=ROUND2, role="anonymous", name="anonymous", team="",
                     action="start", state="backlog", assignee="anonymous")
    assert ROUND2.decide(hole).effect == "allow"
    fixed = situation(rb=TB, role="anonymous", name="anonymous", team="",
                      action="start", state="backlog", assignee="anonymous")
    assert TB.decide(fixed).effect == "deny"
    # and the frozen features catch the draft by name
    failed = [fid for fid, r in features.run_all_pure(ROUND2, FEATURES) if not r.ok]
    assert "feat_working_agreement" in failed and "feat_janitor" in failed
