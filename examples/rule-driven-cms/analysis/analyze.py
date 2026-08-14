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

Every check runs PER ENTITY: a multi-entity rule base (a case and its
comments/attachments) is analyzed entity by entity, each in its own
situation space — a child's space includes the parent-context atoms
(parent.state, parent.same_org, ...) it declared, unconstrained, so a
safety property like "no comment action on a closed case" is proven for
every parent state a rule could ever see. Gate properties carry the same
`entity:` tag as rules (default: the root entity).

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


class EntityAnalysis:
    """One entity's rules, compiled: its symbol table, structural-legality
    formula, per-effect rule formulas, and the 'allowed' predicate."""

    def __init__(self, rb, ent):
        self.ent = ent
        self.sym = SymbolTable(ent.vocabulary)
        assumptions = rb.assumptions_for(ent.name)
        self.assumptions = z3.And(*[a.holds.to_z3(self.sym) for a in assumptions]) \
            if assumptions else z3.BoolVal(True)
        self.legal = self._legal_formula()
        rules = rb.rules_for(ent.name)
        self.denies = [(r, r.when.to_z3(self.sym)) for r in rules if r.effect == "deny"]
        self.allows = [(r, r.when.to_z3(self.sym)) for r in rules if r.effect == "allow"]
        self.any_deny = z3.Or(*[f for _, f in self.denies]) if self.denies else z3.BoolVal(False)
        self.any_allow = z3.Or(*[f for _, f in self.allows]) if self.allows else z3.BoolVal(False)
        self.allowed = z3.And(z3.Not(self.any_deny), self.any_allow)
        self.ctx = z3.And(self.assumptions, self.legal)

    def _legal_formula(self):
        action, state = self.sym.const("action"), self.sym.const("resource.state")
        lit = self.sym.literal
        by_action = {}
        for t in self.ent.transitions:
            by_action.setdefault(t.action, []).append(t.source)
        clauses = [z3.Implies(action == lit("action", a),
                              z3.Or(*[state == lit("resource.state", s) for s in sources]))
                   for a, sources in by_action.items()]
        crud = z3.Or(*[action == lit("action", a) for a in rb_mod.CRUD_ACTIONS])
        clauses.append(z3.Implies(crud, state != lit("resource.state", rb_mod.NO_STATE)))
        return z3.And(*clauses)

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

    def space(self):
        v = self.ent.vocabulary
        n = 2 ** len(v.bools)
        for dom in v.enums.values():
            n *= len(dom)
        return n


class Analyzer:
    def __init__(self, rb, gate_dir):
        self.rb = rb
        self.per_entity = {name: EntityAnalysis(rb, ent)
                           for name, ent in rb.entities.items()}
        self.multi = len(rb.entities) > 1
        with open(f"{gate_dir}/safety.yaml") as f:
            gate = yaml.safe_load(f)
        self.safety = [(p["id"], p.get("description", ""),
                        *self._gate_condition(p, p["requires"]))
                       for p in gate.get("safety", ())]
        self.possibility = [(p["id"], p.get("description", ""),
                             *self._gate_condition(p, p["witness"]))
                            for p in gate.get("possibility", ())]
        self.gate_lifecycle = gate.get("lifecycle") or {}
        self.features_path = f"{gate_dir}/features.yaml"
        self.findings = []

    def _gate_condition(self, prop, source):
        """A gate property is parsed in the vocabulary of the entity it
        names (default: the root) — same tagging as the rules."""
        ent = self.rb.entity_of(prop.get("entity"))
        return ent.name, rb_mod.conditions.parse(source, ent.vocabulary)

    # -- helpers ---------------------------------------------------------------
    def sat(self, *formulas):
        s = z3.Solver()
        s.add(*formulas)
        if s.check() == z3.sat:
            return s.model()
        return None

    def fmt(self, situation):
        return "{" + ", ".join(f"{k}: {str(v).lower()}" for k, v in situation.items()) + "}"

    def fail(self, text):
        self.findings.append(text)
        print(f"   FAIL {text}")

    def tag(self, ent_name):
        return f"[{ent_name}] " if self.multi else ""

    # -- checks ------------------------------------------------------------------
    def check_dead_rules(self):
        print("-- dead rules (does each rule ever change a decision?) --")
        dead = 0
        for name, ea in self.per_entity.items():
            for r, f in ea.allows:
                others = z3.Or(*[g for (o, g) in ea.allows if o.id != r.id]) \
                    if len(ea.allows) > 1 else z3.BoolVal(False)
                if self.sat(ea.ctx, f, z3.Not(ea.any_deny), z3.Not(others)) is None:
                    dead += 1
                    over = [d.id for d, g in ea.denies if self.sat(ea.ctx, f, g) is not None]
                    self.fail(f"{self.tag(name)}DEAD allow rule {r.id!r}: it never grants anything"
                              + (f" (overridden where it overlaps: {', '.join(over)})" if over else ""))
            for r, f in ea.denies:
                others = z3.Or(*[g for (o, g) in ea.denies if o.id != r.id]) \
                    if len(ea.denies) > 1 else z3.BoolVal(False)
                if self.sat(ea.ctx, f, z3.Not(others), ea.any_allow) is None:
                    dead += 1
                    self.fail(f"{self.tag(name)}DEAD deny rule {r.id!r}: it never refuses anything "
                              f"that another rule would have allowed")
        if not dead:
            print(f"   ok: all {len(self.rb.rules)} rules are effectual "
                  f"(each changes at least one decision)")

    def check_authorship(self):
        """Assumptions are axioms — a stale one silently excludes real
        situations from every other check. The one authorship fact the rules
        themselves establish is checkable: any role that can be GRANTED the
        creating transition will be an author at runtime, so the assumptions
        must at least admit it as one."""
        print("-- assumptions: every role that can create must be an assumable author --")
        for name, ea in self.per_entity.items():
            t = ea.ent.creating_transition()
            lit = ea.sym.literal
            action, role = ea.sym.const("action"), ea.sym.const("actor.role")
            is_author = ea.sym.const("actor.is_author")
            creators, stale = [], 0
            for r in self.rb.roles:
                if self.sat(ea.ctx, ea.allowed, action == lit("action", t.action),
                            role == lit("actor.role", r)) is None:
                    continue
                creators.append(r)
                if self.sat(ea.assumptions, role == lit("actor.role", r), is_author) is None:
                    stale += 1
                    self.fail(f"{self.tag(name)}role {r!r} can create items, but the "
                              f"assumptions say it can never be an author — stale "
                              f"assumption: symbolic analysis would silently skip "
                              f"every {r}-authored situation")
            if not stale:
                print(f"   ok: {self.tag(name)}creating roles {creators} "
                      f"are all assumable authors")

    def check_safety(self):
        print("-- safety: must hold in EVERY allowed situation --")
        for pid, _desc, ent_name, cond in self.safety:
            ea = self.per_entity[ent_name]
            model = self.sat(ea.ctx, ea.allowed, z3.Not(cond.to_z3(ea.sym)))
            if model is None:
                print(f"   ok   {self.tag(ent_name)}{pid}")
            else:
                s = ea.situation_of(model)
                self.fail(f"{self.tag(ent_name)}{pid}\n"
                          f"        counterexample: {self.fmt(s)}\n"
                          f"        allowed by: {ea.granting_rule(model)}")

    def check_possibility(self):
        print("-- possibility: must hold in SOME allowed situation --")
        for pid, _desc, ent_name, cond in self.possibility:
            ea = self.per_entity[ent_name]
            model = self.sat(ea.ctx, ea.allowed, cond.to_z3(ea.sym))
            if model is not None:
                s = ea.situation_of(model)
                print(f"   ok   {self.tag(ent_name)}{pid}  witness: {self.fmt(s)} "
                      f"(by {ea.granting_rule(model)})")
            else:
                blockers = []
                for d, _g in ea.denies:
                    rest = z3.Or(*[g for (o, g) in ea.denies if o.id != d.id]) \
                        if len(ea.denies) > 1 else z3.BoolVal(False)
                    without = z3.And(z3.Not(rest), ea.any_allow)
                    if self.sat(ea.ctx, without, cond.to_z3(ea.sym)) is not None:
                        blockers.append(d.id)
                why = f"blocked by deny rule(s): {', '.join(blockers)}" if blockers \
                    else "no allow rule ever grants it"
                self.fail(f"{self.tag(ent_name)}{pid}: IMPOSSIBLE — {why}")

    def check_lifecycle(self):
        print("-- lifecycle: every state reachable, every transition usable --")
        problems = 0
        only_into = self.gate_lifecycle.get("only_into") or {}
        for name, ea in self.per_entity.items():
            lit = ea.sym.literal
            action, state = ea.sym.const("action"), ea.sym.const("resource.state")
            live, dead = [], []
            for t in ea.ent.transitions:
                model = self.sat(ea.ctx, ea.allowed,
                                 action == lit("action", t.action),
                                 state == lit("resource.state", t.source))
                (live if model is not None else dead).append(t)
            for t in dead:
                problems += 1
                self.fail(f"{self.tag(name)}transition {t.action!r} ({t.source} -> "
                          f"{t.target}): no one is ever allowed to take it")
            reachable, frontier = {rb_mod.NO_STATE}, [rb_mod.NO_STATE]
            while frontier:
                here = frontier.pop()
                for t in live:
                    if t.source == here and t.target not in reachable:
                        reachable.add(t.target)
                        frontier.append(t.target)
            for st in ea.ent.states:
                if st not in reachable:
                    problems += 1
                    self.fail(f"{self.tag(name)}state {st!r} is unreachable from creation")
            # gate keys are "state" (the root) or "entity.state"
            for key, via in only_into.items():
                ent_name, _, gated_state = key.rpartition(".")
                if (ent_name or self.rb.root.name) != name:
                    continue
                for t in ea.ent.transitions:
                    if t.target == gated_state and t.action not in via:
                        problems += 1
                        self.fail(f"{self.tag(name)}lifecycle: transition {t.action!r} "
                                  f"({t.source} -> {t.target}) enters {gated_state!r}, "
                                  f"but the gate allows entry only via {via}")
        if not problems:
            n_trans = sum(len(ea.ent.transitions) for ea in self.per_entity.values())
            n_states = sum(len(ea.ent.states) for ea in self.per_entity.values())
            print(f"   ok: {n_trans} transitions live, "
                  f"all {n_states} states reachable, gated entries respected")

    def check_features(self):
        print("-- feature runs (pure decision engine, frozen scenarios) --")
        for fid, result in features_mod.run_all_pure(self.rb, self.features_path):
            if result.ok:
                print(f"   ok   {fid} ({result.message})")
            else:
                self.fail(f"{fid}: {result.message}")

    def run(self):
        rb = self.rb
        n_deny = sum(1 for r in rb.rules if r.effect == "deny")
        n_allow = len(rb.rules) - n_deny
        spaces = {name: ea.space() for name, ea in self.per_entity.items()}
        print(f"== rule-base analysis: {rb.name} ==")
        print(f"rules: {len(rb.rules)} ({n_deny} deny, {n_allow} allow) | "
              f"roles: {len(rb.roles)} | entities: {len(rb.entities)} | "
              f"situation space: {sum(spaces.values())}"
              + (" (" + ", ".join(f"{n}: {s}" for n, s in spaces.items()) + ")"
                 if self.multi else ""))
        self.check_dead_rules()
        self.check_authorship()
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
