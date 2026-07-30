# Reasoning engines: querying invariants for contradictions

**Date:** 2026-07-30  
**Status:** draft

## TL;DR

- **Z3 & CVC5** (SMT solvers): Extract unsat cores mapping directly to contradictory invariants; Python native.
- **Alloy Analyzer**: Bounded relational reasoning generating concrete instances revealing unexpected consequences.
- **Apalache/TLC**: SMT-based & explicit-state model checkers for temporal invariants (init/next/liveness).
- **Clingo** (Answer Set Programming): Consequence finding via `is_consequence()` enumeration.
- **Vacuity checking**: Filter trivial specs (subformulas that don't affect satisfaction); emerging in 2025 LLM property flows.
- **Key gap:** No single tool is perfect; **hybrid pipeline** needed—Z3 for contradiction, Alloy for witness generation, Clingo for surprises.

## Inventory

| Engine | Reasoning Style | Contradiction/Surprise Signal | Automation/API |
|--------|--|--|--|
| Z3 | SAT/SMT (QF_LIA, linear arith., arrays, etc.) | UNSAT core (subset of assertions already unsat) | Python 4.13+, C, Java; checkSat() + getUnsatCore() |
| CVC5 | Multi-theory SMT (QF, quantifiers, datatypes) | UNSAT core extraction; proofs | Python API 1.2.1+ (setOption, checkSat, getUnsatCore) |
| Alloy 6 | Bounded relational first-order + temporal logic | Counterexample instances; instance generation | JAR executable; no native programmatic API; SMT/SAT backend |
| Apalache | Symbolic model checker (SMT-based, bounded k-steps) | Invariant violation traces; unsatisfiable invariants | CLI; TLA+ specs only; SMT solver orchestration |
| TLC | Explicit-state model checker (enumerates reachable states) | Execution traces violating assertions/invariants | CLI; TLA+ only; complete for finite models |
| Clingo | Answer Set Programming (logic rules + constraints) | Consequence queries; absence of solutions = no surprise | Python API (potassco); `is_consequence(lit)` returns True/False/None |
| Vacuity analysis | Property trimming (Boolean reduction) | Subformulas that don't affect truth value | Via model checkers (JasperGold, formal engines); 2025 LLM property flows |

## Per-engine assessment

**Z3 & CVC5:** Best fit for rapid contradiction detection. UNSAT cores directly name contradictory invariants. Python-native APIs enable tight LLM→solver feedback loops. Limited to decidable fragments (e.g., linear arithmetic, uninterpreted functions). CVC5 has modern proof infrastructure. **Win:** fast, programmatic, human-readable cores.

**Alloy Analyzer:** Excellent for relational specs and finite-domain invariants. Instance generation (Alloy's signature strength) reveals surprising consequences you missed—did those two invariants together force an unexpected constraint? **Limitation:** JAR-based CLI, no native programmatic API; requires custom parsing/scraping. **Win:** visual instance explorer, bounded completeness.

**Apalache/TLC:** Purpose-built for TLA+ temporal logic (Init ∧ Next ∧ Inv ∧ Liveness). Handles inductive invariants and concurrent state machines. **Limitation:** steep learning curve; assumes operational spec, not just logical invariants. **Win:** temporal correctness; handles concurrency.

**Clingo:** Logic programming model directly encodes "what must be true" as rules. `is_consequence(literal)` answers "does every model satisfy this?" Complements SAT/SMT for negative results (proving something is NOT a consequence). **Limitation:** less familiar in verification community; requires encoding discipline.

**Vacuity:** Lightweight filter to discard trivial specs (e.g., "A ∨ ¬A" is satisfied regardless of model). 2025 workflows use LLMs to generate properties, then vacuity-check to eliminate noise. **Use:** post-check after solver, not replacement.

## Concrete interaction patterns

```
Pipeline: Invariant → Formal Logic → Engine Query → Results → Developer

1. Developer: "Invariant A: balance ≥ 0. Invariant B: balance ≤ $limit."
2. Translate: ∀t. bal(t) ≥ 0 ∧ bal(t) ≤ limit
3. Name invariants: inv_nonneg, inv_capped
4. Call Z3:
   - Assert inv_nonneg AND inv_capped
   - If UNSAT: getUnsatCore() → [inv_nonneg, inv_capped]
              → Report: "These invariants contradict (e.g., limit = -1)"
   - If SAT: getModel() → Show concrete example (bal=5, limit=10, ...)
5. Call Alloy for witness:
   - Generate instances satisfying all invariants
   - Visualize: shows unexpected relationships
6. Vacuity check:
   - Verify each invariant is referenced in some reachable transition
   - Flag dead invariants ("this is never violated on any trace")
```

## Fit for the workflow

**Step 3 of project brief:** "Query reasoning engine for contradictions/unexpected outcomes *before code*."

**Recommended hybrid:**
1. **Z3** (first): fast contradiction check; unsat core maps invariant names → conflicts
2. **Alloy** (second): witness generation; "show me models satisfying all invariants" → discover surprises
3. **Clingo** (optional): consequence enumeration; "what else must be true?" → find implicit constraints
4. **Vacuity** (polish): filter trivial specs before coding begins

This is **model-based sanity checking**, not code verification (steps 4–5 of the brief).

## Prototype ideas (1–2 day implementations)

1. **Z3 invariant harness** (~4 hours)
   - Parse invariant JSON: `{name, formula_smt2}`
   - Invoke z3 python API; assert all; checkSat()
   - Extract unsat core; pretty-print conflicts
   
2. **Alloy instance inspector** (~6 hours)
   - Translate invariants → Alloy relations + constraints
   - Run `alloy analyze --scope 5`; parse XML output
   - Render instances as tables for dev review

3. **Simple consequence finder** (~4 hours)
   - Encode invariants as Clingo rules
   - Call clingo Python API in "brave" mode
   - Enumerate all derivable facts; flag surprising ones

## Sources

- [Z3 SMT Solver: Advanced Automated Reasoning](https://www.emergentmind.com/topics/z3-smt-solver)
- [CVC5 Python API Documentation](https://cvc5.github.io/docs/cvc5-1.2.1/api/python/pythonic/quickstart.html)
- [Alloy Analyzer Official](https://alloytools.org/)
- [Alloy 6 Release (2025)](https://github.com/informalsystems/apalache)
- [Apalache vs TLC Comparison](https://apalache-mc.org/)
- [Clingo Python API](https://potassco.org/clingo/python-api/current/clingo/solving.html)
- [Vacuity Analysis for Property Qualification (2025)](https://arxiv.org/pdf/2506.17865)
- [Learning Probabilistic Temporal Logic (2025)](https://www.ijcai.org/proceedings/2025/517)
- [Loop Invariant Generation with LLMs & SMT (2025)](https://arxiv.org/pdf/2508.00419)

## Open questions

- **NL-to-formal reliability:** How to avoid LLM drift when translating "balance ≥ 0" to SMT? Need human-in-the-loop review gate?
- **Concurrency:** Brief mentions relaxed consistency & concurrent migrations. Do Z3/CVC5 (decidable fragments) scale to linearizability constraints?
- **Developer feedback loop:** Unsat core is machine-readable; how to render conflicts *for a non-formal developer*?
- **Solver composition:** Can we chain Z3 (contradiction) → Alloy (witness) → Clingo (consequences) in a single pass?
- **Scope/scale:** For 10+ invariants on a web API, what's the complexity wall (SAT hardness vs. bounded instances)?
