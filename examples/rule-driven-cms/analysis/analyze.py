"""Static analysis of a rule base with Z3. This is the review tool: run it
on every change to rules.yaml, before anything is deployed.

    python -m analysis.analyze rulesets/cms
    python -m analysis.analyze rulesets/cms-buggy --gate rulesets/cms

Checks (all findings name rules and print concrete situations — the
counterexamples-as-currency convention of this repo):

  dead rules    for every rule: does ANY situation exist where removing the
                rule would change a decision? A rule that never matters is
                either redundant or — worse — a silently masked intent.
  safety        gate properties that must hold in EVERY allowed situation
                (universally quantified; a violation prints the situation
                and the allow rule that granted it).
  possibility   gate properties that must hold in SOME allowed situation —
                the anti-"safest system does nothing" direction; an
                unsatisfiable one prints which deny rule(s) block it.
  lifecycle     every declared state is reachable and every transition is
                usable by someone (rules x state machine combined).
  features      the frozen scenario file, replayed on the pure decision
                engine, expected denials checked by rule name.

The gate (safety.yaml + features.yaml) can be taken from a DIFFERENT
directory than the rules: that is the frozen-spec contract — agents may
edit rules.yaml; the gate stays pinned.
"""

import argparse
import sys

import yaml
import z3

sys.path.insert(0, __file__.rsplit("/", 2)[0])  # example root, for `engine`

from engine import features as features_mod  # noqa: E402
from engine import rulebase as rb_mod  # noqa: E402


class SymbolTable:
    _instances = 0

    def __init__(self, vocab):
        # Z3 enum sort names are global to the context; tag them per table
        # so several rule bases can be analyzed in one process.
        SymbolTable._instances += 1
        tag = SymbolTable._instances
        self.consts, self.lits = {}, {}
        for var, dom in vocab.enums.items():
            sort, lits = z3.EnumSort(f"{var.replace('.', '_')}_{tag}", list(dom))
            self.consts[var] = z3.Const(var, sort)
            self.lits[var] = dict(zip(dom, lits))
        for var in vocab.bools:
            self.consts[var] = z3.Bool(var)

    def const(self, var):
        return self.consts[var]

    def literal(self, var, value):
        return self.lits[var][value]


SHORT = {"actor.role": "role", "actor.active": "active", "actor.is_author": "is_author",
         "action": "action", "resource.state": "state"}


def shorten(var):
    return SHORT.get(var, var.replace("resource.", ""))


class Analyzer:
    def __init__(self, rb, gate_dir):
        self.rb = rb
        self.sym = SymbolTable(rb.vocabulary)
        self.assumptions = z3.And(*[a.holds.to_z3(self.sym) for a in rb.assumptions]) \
            if rb.assumptions else z3.BoolVal(True)
        self.legal = self._legal_formula()
        self.denies = [(r, r.when.to_z3(self.sym)) for r in rb.rules if r.effect == "deny"]
        self.allows = [(r, r.when.to_z3(self.sym)) for r in rb.rules if r.effect == "allow"]
        self.any_deny = z3.Or(*[f for _, f in self.denies]) if self.denies else z3.BoolVal(False)
        self.any_allow = z3.Or(*[f for _, f in self.allows]) if self.allows else z3.BoolVal(False)
        self.allowed = z3.And(z3.Not(self.any_deny), self.any_allow)
        self.ctx = z3.And(self.assumptions, self.legal)
        with open(f"{gate_dir}/safety.yaml") as f:
            gate = yaml.safe_load(f)
        parse = lambda src: rb_mod.conditions.parse(src, rb.vocabulary)  # noqa: E731
        self.safety = [(p["id"], p.get("description", ""), parse(p["requires"]))
                       for p in gate.get("safety", ())]
        self.possibility = [(p["id"], p.get("description", ""), parse(p["witness"]))
                            for p in gate.get("possibility", ())]
        self.features_path = f"{gate_dir}/features.yaml"
        self.findings = []

    def _legal_formula(self):
        action, state = self.sym.const("action"), self.sym.const("resource.state")
        lit = self.sym.literal
        clauses = [z3.Implies(action == lit("action", t.action),
                              state == lit("resource.state", t.source))
                   for t in self.rb.transitions]
        crud = z3.Or(*[action == lit("action", a) for a in rb_mod.CRUD_ACTIONS])
        clauses.append(z3.Implies(crud, state != lit("resource.state", rb_mod.NO_STATE)))
        return z3.And(*clauses)

    # -- helpers ---------------------------------------------------------------
    def sat(self, *formulas):
        s = z3.Solver()
        s.add(*formulas)
        if s.check() == z3.sat:
            return s.model()
        return None

    def situation_of(self, model):
        out = {}
        for var, const in self.sym.consts.items():
            val = model.eval(const, model_completion=True)
            out[shorten(var)] = str(val) if var in self.sym.lits else z3.is_true(val)
        return out

    def granting_rule(self, model):
        for r, f in self.allows:
            if z3.is_true(model.eval(f, model_completion=True)):
                return r.id
        return "?"

    def fmt(self, situation):
        return "{" + ", ".join(f"{k}: {str(v).lower()}" for k, v in situation.items()) + "}"

    def fail(self, text):
        self.findings.append(text)
        print(f"   FAIL {text}")

    # -- checks ------------------------------------------------------------------
    def check_dead_rules(self):
        print("-- dead rules (does each rule ever change a decision?) --")
        dead = 0
        for r, f in self.allows:
            others = z3.Or(*[g for (o, g) in self.allows if o.id != r.id]) \
                if len(self.allows) > 1 else z3.BoolVal(False)
            if self.sat(self.ctx, f, z3.Not(self.any_deny), z3.Not(others)) is None:
                dead += 1
                over = [d.id for d, g in self.denies if self.sat(self.ctx, f, g) is not None]
                self.fail(f"DEAD allow rule {r.id!r}: it never grants anything"
                          + (f" (overridden where it overlaps: {', '.join(over)})" if over else ""))
        for r, f in self.denies:
            others = z3.Or(*[g for (o, g) in self.denies if o.id != r.id]) \
                if len(self.denies) > 1 else z3.BoolVal(False)
            if self.sat(self.ctx, f, z3.Not(others), self.any_allow) is None:
                dead += 1
                self.fail(f"DEAD deny rule {r.id!r}: it never refuses anything "
                          f"that another rule would have allowed")
        if not dead:
            print(f"   ok: all {len(self.rb.rules)} rules are effectual "
                  f"(each changes at least one decision)")

    def check_safety(self):
        print("-- safety: must hold in EVERY allowed situation --")
        for pid, _desc, cond in self.safety:
            model = self.sat(self.ctx, self.allowed, z3.Not(cond.to_z3(self.sym)))
            if model is None:
                print(f"   ok   {pid}")
            else:
                s = self.situation_of(model)
                self.fail(f"{pid}\n        counterexample: {self.fmt(s)}\n"
                          f"        allowed by: {self.granting_rule(model)}")

    def check_possibility(self):
        print("-- possibility: must hold in SOME allowed situation --")
        for pid, _desc, cond in self.possibility:
            model = self.sat(self.ctx, self.allowed, cond.to_z3(self.sym))
            if model is not None:
                s = self.situation_of(model)
                print(f"   ok   {pid}  witness: {self.fmt(s)} "
                      f"(by {self.granting_rule(model)})")
            else:
                blockers = []
                for d, _g in self.denies:
                    rest = z3.Or(*[g for (o, g) in self.denies if o.id != d.id]) \
                        if len(self.denies) > 1 else z3.BoolVal(False)
                    without = z3.And(z3.Not(rest), self.any_allow)
                    if self.sat(self.ctx, without, cond.to_z3(self.sym)) is not None:
                        blockers.append(d.id)
                why = f"blocked by deny rule(s): {', '.join(blockers)}" if blockers \
                    else "no allow rule ever grants it"
                self.fail(f"{pid}: IMPOSSIBLE — {why}")

    def check_lifecycle(self):
        print("-- lifecycle: every state reachable, every transition usable --")
        lit = self.sym.literal
        action, state = self.sym.const("action"), self.sym.const("resource.state")
        live, dead = [], []
        for t in self.rb.transitions:
            model = self.sat(self.ctx, self.allowed,
                             action == lit("action", t.action),
                             state == lit("resource.state", t.source))
            (live if model is not None else dead).append(t)
        for t in dead:
            self.fail(f"transition {t.action!r} ({t.source} -> {t.target}): "
                      f"no one is ever allowed to take it")
        reachable, frontier = {rb_mod.NO_STATE}, [rb_mod.NO_STATE]
        while frontier:
            here = frontier.pop()
            for t in live:
                if t.source == here and t.target not in reachable:
                    reachable.add(t.target)
                    frontier.append(t.target)
        for st in self.rb.states:
            if st not in reachable:
                self.fail(f"state {st!r} is unreachable from creation")
        if not dead and all(st in reachable for st in self.rb.states):
            print(f"   ok: {len(live)} transitions live, "
                  f"all {len(self.rb.states)} states reachable")

    def check_features(self):
        print("-- feature runs (pure decision engine, frozen scenarios) --")
        for fid, result in features_mod.run_all_pure(self.rb, self.features_path):
            if result.ok:
                print(f"   ok   {fid} ({result.message})")
            else:
                self.fail(f"{fid}: {result.message}")

    def run(self):
        rb = self.rb
        n_deny, n_allow = len(self.denies), len(self.allows)
        n_situations = (len(rb.roles) * 2 * 2 * len(rb.actions)
                        * (len(rb.states) + 1) * (2 ** len(rb.fields)))
        print(f"== rule-base analysis: {rb.name} ==")
        print(f"rules: {len(rb.rules)} ({n_deny} deny, {n_allow} allow) | "
              f"roles: {len(rb.roles)} | states: {len(rb.states)}(+none) | "
              f"actions: {len(rb.actions)} | situation space: {n_situations}")
        self.check_dead_rules()
        self.check_safety()
        self.check_possibility()
        self.check_lifecycle()
        self.check_features()
        if self.findings:
            print(f"VERDICT: FAIL ({len(self.findings)} finding(s))")
            return 1
        print("VERDICT: PASS (0 findings)")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruleset", help="directory containing rules.yaml")
    ap.add_argument("--gate", help="directory containing safety.yaml + features.yaml "
                    "(default: the ruleset directory; point it elsewhere to hold "
                    "edited rules to a FROZEN gate)")
    args = ap.parse_args()
    rb = rb_mod.load(f"{args.ruleset}/rules.yaml")
    analyzer = Analyzer(rb, args.gate or args.ruleset)
    sys.exit(analyzer.run())


if __name__ == "__main__":
    main()
