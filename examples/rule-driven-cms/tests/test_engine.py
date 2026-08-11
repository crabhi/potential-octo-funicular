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

@pytest.mark.parametrize("rb", [CMS, TICKETS], ids=["cms", "tickets"])
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
