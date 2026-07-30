"""CLI for the P2 invariant oracle.

    python -m oracle check FILE [--json]
    python -m oracle witness FILE [-n K] [--json]
    python -m oracle vacuity FILE [--json]
    python -m oracle claim FILE --claim EXPR [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from . import engine
from .expr import ExprError
from .schema import Model, SchemaError, load_model


def render_table(rows: List[Dict[str, Any]], variables) -> str:
    if not rows:
        return "(no rows)"
    cols = list(variables.keys())
    widths = {c: len(c) for c in cols}
    for r in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(r[c])))
    lines = ["  ".join(c.ljust(widths[c]) for c in cols)]
    lines.append("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        lines.append("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    return "\n".join(lines)


def _describe(model: Model, name: str) -> str:
    try:
        return model.invariant(name).description
    except KeyError:
        return ""


# -- subcommands ----------------------------------------------------------


def cmd_check(args) -> int:
    model = load_model(args.file)
    result = engine.check_consistency(model)
    if result["satisfiable"]:
        payload = {"verdict": "CONSISTENT", "witness": result["model"]}
    else:
        payload = {
            "verdict": "IMPOSSIBLE",
            "unsat_core": [
                {"name": n, "description": _describe(model, n)} for n in result["unsat_core"]
            ],
        }
    if args.json:
        print(json.dumps(payload, indent=2))
    elif result["satisfiable"]:
        print("Verdict: CONSISTENT")
        print()
        print("Witness model:")
        print(render_table([result["model"]], model.variables))
    else:
        print("Verdict: IMPOSSIBLE")
        print()
        print("Unsat core (minimal conflicting invariants):")
        for entry in payload["unsat_core"]:
            print(f"  - {entry['name']}: {entry['description']}")
    return 0 if result["satisfiable"] else 1


def cmd_witness(args) -> int:
    model = load_model(args.file)
    feas = engine.check_consistency(model)
    if not feas["satisfiable"]:
        payload = {"verdict": "IMPOSSIBLE", "unsat_core": feas["unsat_core"]}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("Verdict: IMPOSSIBLE -- no witnesses; invariants are contradictory")
            for n in feas["unsat_core"]:
                print(f"  - {n}: {_describe(model, n)}")
        return 1

    witnesses = engine.enumerate_witnesses(model, args.n)
    payload = {"verdict": "CONSISTENT", "requested": args.n, "found": len(witnesses), "witnesses": witnesses}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Verdict: CONSISTENT -- found {len(witnesses)} distinct witness model(s) (requested {args.n})")
        print()
        print(render_table(witnesses, model.variables))
    return 0


def cmd_vacuity(args) -> int:
    model = load_model(args.file)
    result = engine.vacuity_check(model)
    if not result["feasible"]:
        payload = {"verdict": "IMPOSSIBLE", "detail": "invariant set is unsatisfiable; vacuity check skipped"}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("Verdict: IMPOSSIBLE -- invariant set itself is unsatisfiable; run `check` to see the conflict.")
        return 1

    payload = {"results": result["results"]}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        width = max((len(r["name"]) for r in result["results"]), default=0)
        for r in result["results"]:
            desc = _describe(model, r["name"])
            print(f"  {r['name'].ljust(width)}  {r['verdict']:<10s} {desc}")
    return 0


def cmd_claim(args) -> int:
    model = load_model(args.file)
    try:
        claim_term = model.compiler.compile(args.claim)
    except Exception as e:
        print(f"error compiling claim: {e}", file=sys.stderr)
        return 2
    result = engine.claim_check(model, claim_term)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Verdict: {result['verdict']}")
        print(result.get("detail", ""))
        for key in ("witness", "witness_claim_true", "witness_claim_false"):
            w = result.get(key)
            if w:
                print()
                print(f"{key}:")
                print(render_table([w], model.variables))
    return 0 if result["verdict"] in ("VALID",) else (1 if result["verdict"] == "IMPOSSIBLE" else 0)


# -- argparse wiring --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="oracle",
        description="Invariant oracle: contradiction / redundancy / vacuity / claim checking over Z3.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c1 = sub.add_parser("check", help="assert all invariants; report CONSISTENT or IMPOSSIBLE (+ unsat core)")
    c1.add_argument("file")
    c1.add_argument("--json", action="store_true")
    c1.set_defaults(func=cmd_check)

    c2 = sub.add_parser("witness", help="enumerate up to K diverse satisfying models")
    c2.add_argument("file")
    c2.add_argument("-n", type=int, default=5, help="max number of models to enumerate (default 5)")
    c2.add_argument("--json", action="store_true")
    c2.set_defaults(func=cmd_witness)

    c3 = sub.add_parser("vacuity", help="per-invariant REDUNDANT / TAUTOLOGY / OK report")
    c3.add_argument("file")
    c3.add_argument("--json", action="store_true")
    c3.set_defaults(func=cmd_vacuity)

    c4 = sub.add_parser("claim", help="VALID / INVALID / SATISFIABLE / IMPOSSIBLE verdict for a claim")
    c4.add_argument("file")
    c4.add_argument("--claim", required=True, help="expression in the same mini-language as invariant formulas")
    c4.add_argument("--json", action="store_true")
    c4.set_defaults(func=cmd_claim)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SchemaError, ExprError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
