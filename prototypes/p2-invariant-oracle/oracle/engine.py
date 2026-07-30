"""Z3 queries: contradiction (unsat core), witness enumeration, vacuity,
and claim verdicts (Bedrock-Automated-Reasoning-style taxonomy).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import z3

from .schema import Model, VarSpec


def _new_solver(model: Model) -> z3.Solver:
    s = z3.Solver()
    for c in model.domain_constraints:
        s.add(c)
    return s


def render_value(spec: VarSpec, val: Any):
    if spec.type == "bool":
        return z3.is_true(val)
    if spec.type == "int":
        return val.as_long()
    if spec.type == "enum":
        for name, const in spec.consts.items():
            if z3.eq(val, const):
                return name
        return str(val)
    return str(val)


def extract_model(model: Model, zmodel: z3.ModelRef) -> Dict[str, Any]:
    out = {}
    for name, spec in model.variables.items():
        val = zmodel.eval(spec.z3var, model_completion=True)
        out[name] = render_value(spec, val)
    return out


def check_consistency(model: Model) -> Dict[str, Any]:
    """Assert every invariant (tracked) plus domain constraints.

    Returns {"satisfiable": bool, "model": {...}|None, "unsat_core": [names]|None}.
    """
    s = _new_solver(model)
    track_names: Dict[str, str] = {}
    for inv in model.invariants:
        p = z3.Bool(f"track__{inv.name}")
        s.assert_and_track(inv.term, p)
        track_names[p.decl().name()] = inv.name

    result = s.check()
    if result == z3.sat:
        return {"satisfiable": True, "model": extract_model(model, s.model()), "unsat_core": None}
    if result == z3.unsat:
        order = {inv.name: i for i, inv in enumerate(model.invariants)}
        core_names = {track_names[p.decl().name()] for p in s.unsat_core()}
        names = sorted(core_names, key=lambda n: order[n])
        return {"satisfiable": False, "model": None, "unsat_core": names}
    raise RuntimeError(f"z3 returned unknown: {s.reason_unknown()}")


def enumerate_witnesses(model: Model, k: int) -> List[Dict[str, Any]]:
    """Up to k distinct satisfying models, blocking each exact prior assignment."""
    s = _new_solver(model)
    for inv in model.invariants:
        s.add(inv.term)
    witnesses: List[Dict[str, Any]] = []
    while len(witnesses) < k and s.check() == z3.sat:
        m = s.model()
        witnesses.append(extract_model(model, m))
        block = [
            spec.z3var != m.eval(spec.z3var, model_completion=True)
            for spec in model.variables.values()
        ]
        s.add(z3.Or(*block))
    return witnesses


def vacuity_check(model: Model) -> Dict[str, Any]:
    """Per invariant: TAUTOLOGY (always true, even alone), REDUNDANT (implied
    by the others), or OK. Skipped (feasible=False) if the base set is unsat.
    """
    base = _new_solver(model)
    for inv in model.invariants:
        base.add(inv.term)
    if base.check() != z3.sat:
        return {"feasible": False, "results": []}

    results = []
    for i, inv in enumerate(model.invariants):
        others = [o.term for j, o in enumerate(model.invariants) if j != i]

        s_taut = _new_solver(model)
        s_taut.add(z3.Not(inv.term))
        is_tautology = s_taut.check() == z3.unsat

        s_red = _new_solver(model)
        for o in others:
            s_red.add(o)
        s_red.add(z3.Not(inv.term))
        is_redundant = s_red.check() == z3.unsat

        if is_tautology:
            verdict = "TAUTOLOGY"
        elif is_redundant:
            verdict = "REDUNDANT"
        else:
            verdict = "OK"
        results.append({"name": inv.name, "verdict": verdict})
    return {"feasible": True, "results": results}


def claim_check(model: Model, claim_term) -> Dict[str, Any]:
    """Bedrock-style verdict: VALID / INVALID / SATISFIABLE / IMPOSSIBLE."""
    base = _new_solver(model)
    for inv in model.invariants:
        base.add(inv.term)
    if base.check() != z3.sat:
        return {"verdict": "IMPOSSIBLE", "detail": "the invariant set itself is unsatisfiable"}

    s_neg = _new_solver(model)
    for inv in model.invariants:
        s_neg.add(inv.term)
    s_neg.add(z3.Not(claim_term))
    r_neg = s_neg.check()
    witness_claim_false = extract_model(model, s_neg.model()) if r_neg == z3.sat else None

    s_pos = _new_solver(model)
    for inv in model.invariants:
        s_pos.add(inv.term)
    s_pos.add(claim_term)
    r_pos = s_pos.check()
    witness_claim_true = extract_model(model, s_pos.model()) if r_pos == z3.sat else None

    if r_neg == z3.unsat:
        return {
            "verdict": "VALID",
            "detail": "invariants entail the claim (no model satisfies invariants and not(claim))",
            "witness": witness_claim_true,
        }
    if r_pos == z3.unsat:
        return {
            "verdict": "INVALID",
            "detail": "invariants entail the negation of the claim (no model satisfies invariants and claim)",
            "witness": witness_claim_false,
        }
    return {
        "verdict": "SATISFIABLE",
        "detail": "both the claim and its negation are consistent with the invariants",
        "witness_claim_true": witness_claim_true,
        "witness_claim_false": witness_claim_false,
    }
