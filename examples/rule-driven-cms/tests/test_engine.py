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


# --- multiple entity types: children with parent context ---------------------

MULTI = rulebase.RuleBase({
    "entity": "case",
    "roles": ["member", "admin"],
    "states": ["open", "closed"],
    "fields": [{"name": "team", "has": False}],
    "actor_fields": ["team"],
    "projections": [{"name": "same_team", "kind": "actor_matches_field",
                     "actor_attr": "team", "field": "team"}],
    "lifecycle": {"transitions": [
        {"action": "create", "from": "none", "to": "open"},
        {"action": "close", "from": "open", "to": "closed"}]},
    "children": [{
        "entity": "note",
        "states": ["posted"],
        "fields": ["body"],
        "context": ["state", "is_author", "same_team"],
        "lifecycle": {"transitions": [
            {"action": "post", "from": "none", "to": "posted"}]},
    }],
    "rules": [
        {"id": "own_team_only", "effect": "deny",
         "when": 'actor.role == "member" and not resource.same_team'},
        {"id": "member_case", "effect": "allow",
         "when": 'actor.role == "member" and action in ["read", "edit", "create", "close"]'},
        {"id": "admin_case", "effect": "allow",
         "when": 'actor.role == "admin"'},
        {"id": "own_team_notes", "entity": "note", "effect": "deny",
         "when": 'actor.role == "member" and not parent.same_team'},
        {"id": "sealed_thread", "entity": "note", "effect": "deny",
         "when": 'parent.state == "closed" and action != "read"'},
        {"id": "note_needs_body", "entity": "note", "effect": "deny",
         "when": 'action == "post" and not resource.has_body'},
        {"id": "member_notes", "entity": "note", "effect": "allow",
         "when": 'actor.role == "member" and action in ["read", "post"]'},
    ],
}, name="multi")


def test_child_entities_load_and_the_root_view_is_unchanged():
    assert set(MULTI.entities) == {"case", "note"}
    # single-entity API still answers for the root
    assert MULTI.entity == "case" and MULTI.fields == ("team",)
    assert MULTI.creating_transition().action == "create"
    note = MULTI.entity_of("note")
    assert note.parent is MULTI.root
    assert MULTI.vocabulary.enums.keys() != note.vocabulary.enums.keys()
    assert note.vocabulary.enums["parent.state"] == ("open", "closed")  # no 'none'
    assert "parent.same_team" in note.vocabulary.bools
    assert "parent.is_author" in note.vocabulary.bools


def test_multi_entity_load_errors():
    def doc(**over):
        import copy
        d = {"entity": "a", "roles": ["r"], "states": ["s"], "fields": [],
             "lifecycle": {"transitions": [{"action": "make", "from": "none", "to": "s"}]},
             "children": [copy.deepcopy(over.pop("child", {
                 "entity": "b", "states": ["t"], "fields": [],
                 "lifecycle": {"transitions": [{"action": "add", "from": "none", "to": "t"}]}}))],
             "rules": [{"id": "r1", "effect": "allow", "when": 'actor.active'}]}
        d.update(over)
        return d
    rulebase.RuleBase(doc(), name="ok")  # the baseline loads
    with pytest.raises(rulebase.RuleBaseError):  # unknown context atom
        rulebase.RuleBase(doc(child={
            "entity": "b", "states": ["t"], "fields": [], "context": ["ghost"],
            "lifecycle": {"transitions": [{"action": "add", "from": "none", "to": "t"}]}}), "x")
    with pytest.raises(rulebase.RuleBaseError):  # children of children
        rulebase.RuleBase(doc(child={
            "entity": "b", "states": ["t"], "fields": [], "children": [],
            "lifecycle": {"transitions": [{"action": "add", "from": "none", "to": "t"}]}}), "x")
    with pytest.raises(rulebase.RuleBaseError):  # rule tagged for a ghost entity
        rulebase.RuleBase(doc(rules=[{"id": "r1", "entity": "ghost",
                                      "effect": "allow", "when": "actor.active"}]), "x")
    with pytest.raises(rulebase.RuleBaseError):  # root cannot declare context
        rulebase.RuleBase(doc(context=["state"]), "x")


def test_child_situation_carries_parent_context():
    note = MULTI.entity_of("note")
    parent = {"state": "open", "author": "tom", "team": "argo"}
    s = note.situation("member", True, True, "post", "none", {"body": "b"},
                       actor_attrs={"name": "tom", "team": "argo"}, parent=parent)
    assert s["parent.state"] == "open"
    assert s["parent.is_author"] and s["parent.same_team"]
    s2 = note.situation("member", True, False, "read", "posted", {"body": "b"},
                        actor_attrs={"name": "nadia", "team": "boreal"}, parent=parent)
    assert not s2["parent.is_author"] and not s2["parent.same_team"]
    with pytest.raises(ValueError):  # context without the parent row is a bug
        note.situation("member", True, True, "post", "none", {"body": "b"})


def test_backends_agree_on_every_situation_per_entity():
    for ent_name, ent in MULTI.entities.items():
        sym = SymbolTable(ent.vocabulary)
        conds = [r.when for r in MULTI.rules_for(ent_name)] \
            + [a.holds for a in MULTI.assumptions_for(ent_name)]
        compiled = [c.to_z3(sym) for c in conds]
        for s in ent.all_situations():
            subst = []
            for var, const in sym.consts.items():
                if var in sym.lits:
                    subst.append((const, sym.lits[var][s[var]]))
                else:
                    subst.append((const, z3.BoolVal(s[var])))
            for cond, f in zip(conds, compiled):
                z3_val = z3.is_true(z3.simplify(z3.substitute(f, *subst)))
                assert cond.evaluate(s) == z3_val, (ent_name, cond.source, s)


def make_multi_kernel():
    actors = {
        "tom": features.Actor("tom", "member", True, {"team": "argo"}),
        "nadia": features.Actor("nadia", "member", True, {"team": "boreal"}),
        "root": features.Actor("root", "admin", True, {"team": ""}),
    }
    conn = store_mod.open_db(":memory:", MULTI, actors)
    return kernel_mod.Kernel(MULTI, conn), actors


def test_kernel_joins_the_parent_into_child_decisions():
    k, a = make_multi_kernel()
    case = k.create(a["tom"], {"team": "argo"})
    note = k.create(a["tom"], {"body": "hi"}, entity="note", parent_id=case["id"])
    assert note["parent_id"] == case["id"] and note["state"] == "posted"
    # the other team's member is walled off the thread by the PARENT's team
    with pytest.raises(kernel_mod.Denied) as e:
        k.get(a["nadia"], note["id"], entity="note")
    assert e.value.rule.id == "own_team_notes"
    with pytest.raises(kernel_mod.Denied) as e:
        k.create(a["nadia"], {"body": "hey"}, entity="note", parent_id=case["id"])
    assert e.value.rule.id == "own_team_notes"
    thread = k.visible(a["tom"], entity="note", parent_id=case["id"])
    assert [r["id"] for r in thread] == [note["id"]]
    assert k.visible(a["nadia"], entity="note", parent_id=case["id"]) == []
    # a child needs its parent named; the root refuses one
    with pytest.raises(ValueError):
        k.create(a["tom"], {"body": "x"}, entity="note")
    with pytest.raises(ValueError):
        k.create(a["tom"], {"team": "argo"}, parent_id=case["id"])


def test_closing_the_parent_seals_the_thread_live():
    k, a = make_multi_kernel()
    case = k.create(a["tom"], {"team": "argo"})
    k.create(a["tom"], {"body": "before"}, entity="note", parent_id=case["id"])
    k.act(a["tom"], "close", case["id"])
    # same call that just succeeded — the parent's new state now refuses it
    with pytest.raises(kernel_mod.Denied) as e:
        k.create(a["tom"], {"body": "after"}, entity="note", parent_id=case["id"])
    assert e.value.rule.id == "sealed_thread"
    # ... but the record stays readable: context-sensitivity, not lockout
    assert len(k.visible(a["tom"], entity="note", parent_id=case["id"])) == 1


def test_parent_delete_cascades_to_children():
    # the known sharp edge, pinned: deleting a parent removes its children
    # WITHOUT consulting the children's own delete rules (research note 16)
    k, a = make_multi_kernel()
    case = k.create(a["tom"], {"team": "argo"})
    note = k.create(a["tom"], {"body": "hi"}, entity="note", parent_id=case["id"])
    k.delete(a["root"], case["id"])
    assert k.get(a["root"], case["id"]) is None
    assert k.get(a["root"], note["id"], entity="note") is None


def test_feature_steps_reach_child_entities():
    actors = {"tom": features.Actor("tom", "member", True, {"team": "argo"}),
              "nadia": features.Actor("nadia", "member", True, {"team": "boreal"})}
    ex = features.PureExecutor(MULTI, actors)
    res = ex.run({"steps": [
        {"actor": "tom", "action": "create", "set": {"team": "argo"}, "expect": "allow"},
        {"actor": "tom", "entity": "note", "action": "post", "expect": "deny",
         "denied_by": "note_needs_body"},
        {"actor": "tom", "entity": "note", "action": "post", "set": {"body": "hi"},
         "expect": "allow", "state_after": "posted"},
        {"actor": "nadia", "entity": "note", "action": "read", "expect": "deny",
         "denied_by": "own_team_notes"},
        {"actor": "tom", "action": "close", "expect": "allow", "state_after": "closed"},
        {"actor": "tom", "entity": "note", "action": "post", "set": {"body": "x"},
         "expect": "deny", "denied_by": "sealed_thread"},
        {"actor": "tom", "entity": "note", "action": "read", "expect": "allow"},
    ]})
    assert res.ok, res.message


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
