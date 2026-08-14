"""Engine unit tests. The important one is exhaustive backend agreement:
the finite situation space is small enough to enumerate completely, so the
claim "the analyzer reasons about exactly what the server enforces" is
checked for EVERY situation and every condition — not sampled."""

import pathlib
import sys

import pytest
import z3

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.analyze import SymbolTable  # noqa: E402
from engine import conditions, features, rulebase  # noqa: E402

CMS = rulebase.load(ROOT / "rulesets/cms/rules.yaml")
TICKETS = rulebase.load(ROOT / "rulesets/tickets/rules.yaml")
RECEIVABLES = rulebase.load(ROOT / "rulesets/receivables/rules.yaml")


# --- condition language -------------------------------------------------------

def test_condition_typos_are_load_errors():
    v = CMS.vocabulary
    for bad in [
        'actor.rle == "admin"',          # unknown variable
        'actor.role == "editer"',        # constant outside the enum domain
        'actor.role',                    # enum used as a bare boolean
        'actor.role == action',          # comparing two variables
        'f(actor.active)',               # arbitrary calls
        'actor.role == "admin" if 1 else 0',
    ]:
        with pytest.raises(conditions.ConditionError):
            conditions.parse(bad, v)


def test_condition_evaluation():
    v = CMS.vocabulary
    s = CMS.situation("editor", True, False, "publish", "in_review",
                      {"title": "t", "body": ""})
    assert conditions.parse('actor.role == "editor"', v).evaluate(s)
    assert conditions.parse('action in ["publish", "reject"]', v).evaluate(s)
    assert not conditions.parse('actor.is_author', v).evaluate(s)
    assert conditions.parse('resource.has_title and not resource.has_body', v).evaluate(s)
    assert conditions.parse('implies(actor.is_author, actor.active)', v).evaluate(s)


# --- exhaustive two-backend agreement ------------------------------------------

@pytest.mark.parametrize("rb", [CMS, TICKETS, RECEIVABLES],
                         ids=["cms", "tickets", "receivables"])
def test_backends_agree_on_every_situation(rb):
    sym = SymbolTable(rb.vocabulary)
    conds = [r.when for r in rb.rules] + [a.holds for a in rb.assumptions]
    compiled = [c.to_z3(sym) for c in conds]
    checked = 0
    for s in rb.all_situations():
        subst = []
        for var, const in sym.consts.items():
            if var in sym.lits:
                subst.append((const, sym.lits[var][s[var]]))
            else:
                subst.append((const, z3.BoolVal(s[var])))
        for cond, f in zip(conds, compiled):
            z3_val = z3.is_true(z3.simplify(z3.substitute(f, *subst)))
            assert cond.evaluate(s) == z3_val, (cond.source, s)
            checked += 1
    assert checked == sum(1 for _ in rb.all_situations()) * len(conds)


# --- decision semantics ---------------------------------------------------------

def situation(**kw):
    base = dict(role="author", active=True, is_author=True, action="read",
                state="draft", fields={"title": "t", "body": "b"})
    base.update(kw)
    return CMS.situation(base["role"], base["active"], base["is_author"],
                         base["action"], base["state"], base["fields"])


def test_deny_overrides_allow():
    # admin_all allows everything, but separation of duties still denies
    v = CMS.decide(situation(role="admin", action="publish", state="in_review"))
    assert v.effect == "deny" and v.id == "no_self_decision"


def test_default_deny_is_named():
    v = CMS.decide(situation(role="viewer", is_author=False))
    assert v.effect == "deny" and v.id == "default_deny"


def test_happy_path_allows():
    v = CMS.decide(situation(role="editor", is_author=False,
                             action="publish", state="in_review"))
    assert v.effect == "allow" and v.id == "editor_decide"


def test_lifecycle_legality():
    assert CMS.lifecycle_legal("publish", "in_review")
    assert not CMS.lifecycle_legal("publish", "draft")
    assert CMS.lifecycle_legal("create", "none")
    assert not CMS.lifecycle_legal("edit", "none")


# --- feature runs ----------------------------------------------------------------

def test_cms_features_pass_purely():
    for fid, result in features.run_all_pure(CMS, ROOT / "rulesets/cms/features.yaml"):
        assert result.ok, (fid, result.message)


def test_buggy_rules_fail_frozen_features():
    buggy = rulebase.load(ROOT / "rulesets/cms-buggy/rules.yaml")
    results = features.run_all_pure(buggy, ROOT / "rulesets/cms/features.yaml")
    failed = [fid for fid, r in results if not r.ok]
    assert "feat_publish_lifecycle" in failed   # strict_privacy kills review
    assert "feat_no_self_publish" in failed     # missing deny caught by expected-denial


# --- time (projections + multi-source transitions) -------------------------------

def test_date_projection_follows_the_clock():
    fields = {"amount": "10", "payer_name": "X", "reference": "",
              "due_date": "2026-08-15"}
    s_before = RECEIVABLES.situation("clock", True, False, "mark_overdue",
                                     "awaiting", fields, today="2026-08-11")
    s_after = RECEIVABLES.situation("clock", True, False, "mark_overdue",
                                    "awaiting", fields, today="2026-09-10")
    assert not s_before["resource.is_past_due"]
    assert s_after["resource.is_past_due"]
    assert RECEIVABLES.decide(s_before).id == "no_premature_overdue"
    assert RECEIVABLES.decide(s_after).id == "clock_works"


def test_multi_source_transition_legality():
    assert RECEIVABLES.lifecycle_legal("settle", "awaiting")
    assert RECEIVABLES.lifecycle_legal("settle", "overdue")
    assert not RECEIVABLES.lifecycle_legal("settle", "paid")
    assert RECEIVABLES.transition_for("settle", "overdue").target == "paid"


# --- relations (actor fields + actor_matches_field) -------------------------------

MINI = rulebase.RuleBase({
    "entity": "thing",
    "roles": ["member", "admin"],
    "states": ["open"],
    "fields": ["title", {"name": "team", "has": False},
               {"name": "assignee", "has": False}],
    "actor_fields": ["team"],
    "projections": [
        {"name": "same_team", "kind": "actor_matches_field",
         "actor_attr": "team", "field": "team"},
        {"name": "is_assignee", "kind": "actor_matches_field",
         "actor_attr": "name", "field": "assignee"},
    ],
    "lifecycle": {"transitions": [{"action": "create", "from": "none", "to": "open"}]},
    "rules": [{"id": "own_team_only", "effect": "deny",
               "when": 'actor.role == "member" and not resource.same_team'},
              {"id": "member_all", "effect": "allow",
               "when": 'actor.role == "member"'}],
}, name="mini")


def test_has_opt_out_trims_the_vocabulary():
    assert MINI.fields == ("title", "team", "assignee")
    assert "resource.has_title" in MINI.vocabulary.bools
    assert "resource.has_team" not in MINI.vocabulary.bools
    assert "resource.has_assignee" not in MINI.vocabulary.bools



# --- the kernel: the verified boundary as a function-level API --------------------

from engine import kernel as kernel_mod  # noqa: E402
from engine import store as store_mod  # noqa: E402


def make_kernel():
    actors = {
        "tom": features.Actor("tom", "member", True, {"team": "argo"}),
        "nadia": features.Actor("nadia", "member", True, {"team": "boreal"}),
    }
    conn = store_mod.open_db(":memory:", MINI, actors)
    return kernel_mod.Kernel(MINI, conn), actors


def test_kernel_decides_before_it_touches_state():
    k, a = make_kernel()
    row = k.create(a["tom"], {"title": "t", "team": "argo", "assignee": "tom"})
    assert row["state"] == "open"
    # reads are decided: the other team's member gets a typed, named refusal
    with pytest.raises(kernel_mod.Denied) as e:
        k.get(a["nadia"], row["id"])
    assert e.value.rule.id == "own_team_only"
    assert [r["id"] for r in k.visible(a["tom"])] == [row["id"]]
    assert k.visible(a["nadia"]) == []
    # create is decided on the proposed fields, before anything exists
    with pytest.raises(kernel_mod.Denied) as e:
        k.create(a["nadia"], {"title": "t", "team": "argo"})
    assert e.value.rule.id == "own_team_only"


def test_kernel_edit_decides_what_the_row_would_become():
    k, a = make_kernel()
    row = k.create(a["tom"], {"title": "t", "team": "argo"})
    # tom may edit the row — but the row may not BECOME another team's:
    # the second decision closes the "edit is blind to values" gap
    with pytest.raises(kernel_mod.Denied) as e:
        k.edit(a["tom"], row["id"], {"team": "boreal"})
    assert e.value.rule.id == "own_team_only"
    assert k.get(a["tom"], row["id"])["team"] == "argo"  # nothing was written
    row = k.edit(a["tom"], row["id"], {"title": "renamed"})
    assert row["title"] == "renamed"


def test_kernel_affordances_and_default_deny():
    k, a = make_kernel()
    row = k.create(a["tom"], {"title": "t", "team": "argo"})
    ghost = features.Actor("ada", "admin", True, {"team": ""})
    d = k.decide(ghost, "read", row)
    assert not d.allowed and d.rule.id == "default_deny"
    acts = dict(k.affordances(a["nadia"], row))
    assert all(not d.allowed for d in acts.values())
    assert {d.rule.id for d in acts.values()} == {"own_team_only"}


def test_kernel_hides_its_connection():
    k, _ = make_kernel()
    assert not hasattr(k, "conn") and not hasattr(k, "_conn")


def test_actor_matches_field_projection():
    fields = {"title": "t", "team": "argo", "assignee": "tom"}
    s = MINI.situation("member", True, False, "read", "open", fields,
                       actor_attrs={"name": "tom", "team": "argo"})
    assert s["resource.same_team"] and s["resource.is_assignee"]
    assert MINI.decide(s).effect == "allow"
    s = MINI.situation("member", True, False, "read", "open", fields,
                       actor_attrs={"name": "nadia", "team": "boreal"})
    assert not s["resource.same_team"] and not s["resource.is_assignee"]
    assert MINI.decide(s).id == "own_team_only"
    # empty never matches: a team-less resource belongs to nobody
    s = MINI.situation("member", True, False, "read", "open",
                       {"title": "t", "team": "", "assignee": ""},
                       actor_attrs={"name": "tom", "team": "argo"})
    assert not s["resource.same_team"] and not s["resource.is_assignee"]
