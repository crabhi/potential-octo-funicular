# Synthesis: candidate architectures & recommendation

Date: 2026-07-30. Status: draft — awaiting developer decision (M2).
Inputs: notes 01–06.

## The pipeline (tool-agnostic)

```
 developer                LLM                     reasoning engine
 ─────────                ───                     ────────────────
 1. invariants (NL) ──► 2. formal spec ──review──► 3. consistency &
                            (draft)      (dev)       consequence queries
                                                      │  contradictions?
                                                      │  vacuous invariants?
                                                      │  surprising traces?
                                                      ▼
                                         4. model check the DESIGN
                                            (concurrent requests + online
                                             migration, small bounds)
                                                      │
                                                      ▼
                                         5. bind spec to IMPLEMENTATION
                                            (conformance layer: trace
                                             checking / model-based tests /
                                             code-level proofs)
                                                      │
                                                      ▼
                                         6. agent optimization loop:
                                            propose edit → conformance
                                            gate must stay green →
                                            measure objective (perf) →
                                            keep or revert
```

## Design decisions, resolved from the research

### D1 — Spec language (what the LLM writes, the developer reviews)

Findings (notes 01, 06):
- TLA-family semantics (TLA+/PlusCal or **Quint**) is the best fit for the
  domain: concurrency + refinement (serializable → concurrent) are
  first-class, checkers emit JSON counterexamples, and there is a public
  worked example of exactly our scenario (zero-downtime migration +
  concurrent requests in PlusCal).
- One-shot NL→TLA+ by LLMs is unreliable (~8.6–46% semantic correctness
  across 2025/26 benchmarks) even though syntax is nearly always valid.
  The only strategy that works is **progressive, checker-in-the-loop
  authoring** — which is exactly what an agent harness can do.
- Quint ships an official **LLM Kit** (Claude Code agents for spec
  generation/repair) and the Apalache symbolic backend; P has an MCP server
  and AWS production pedigree but forces an actor/message framing.
- AWS Bedrock Automated Reasoning (note 06) shows the industrial-strength
  alternative: a **restricted typed rule schema** (bools/ints/enums,
  implications, SMT-LIB subset) that LLMs translate into far more reliably
  than full spec languages, reviewed via "fidelity reports" that ground each
  rule back to the source sentence.

Decision proposal: **two-layer spec**. Developer-facing invariants live in a
small typed schema (reviewable sentence-by-sentence, LLM-translatable with
high fidelity); the concurrency/migration machinery lives in a TLA-family
model (Quint preferred, TLA+ fallback) authored agentically with the checker
in the loop. The typed invariants compile into the model's invariant section.

### D2 — Consistency oracle ("query for contradictions / unexpected outcomes")

Findings (notes 04, 06): no tool has this as a first-class feature; it is a
thin composition of standard capabilities:
- **Contradiction**: assert all invariants in Z3/CVC5 → if UNSAT, the
  **unsat core** names the minimal conflicting subset.
- **Unexpected outcomes**: enumerate satisfying instances/traces
  (Alloy instances, Apalache/Quint simulator runs) and show them to the
  developer as "did you expect this to be allowed?".
- **Vacuity**: check each invariant can actually be violated by some
  perturbed system (else it's dead weight or mis-translated).
- Return a rich verdict taxonomy, not pass/fail — Bedrock's
  `VALID / INVALID / SATISFIABLE / IMPOSSIBLE / TRANSLATION_AMBIGUOUS`
  is the template.

Decision proposal: build a small **invariant-oracle CLI** wrapping Z3 (cores)
plus the model checker's simulator (witness traces), with the taxonomy above
as its output contract. This is genuinely novel glue and cheap to prototype.

### D3 — Modeling concurrent requests + online migration

Findings (note 05): the F1 paper (Rae et al., VLDB 2013) is the only formal
treatment of online schema change — orphan-data/integrity anomalies,
`Absent → WriteOnly → Present → DeleteOnly` element states, ≤1 version-skew
invariant. Modern tools (pgroll, Reshape, gh-ost) implement expand/contract
with **zero published formal argument** — a real gap this project can fill.
Isolation semantics should be **reused, not re-derived**: existing TLA+
snapshot-isolation specs + Crooks-style client-centric definitions; none
model DDL, so adding the schema-version dimension is the novel, tractable
piece. The refinement path matches the brief: prove schema-state invariants
under serializability first, then relax to SI/READ COMMITTED and re-check.

### D4 — Spec ↔ implementation conformance (making green mean something)

Findings (note 02): layered, in order of adoption cost:
1. **Model-based testing against the real API** (Hypothesis stateful /
   Schemathesis): cheapest, drives real HTTP, migration = just another rule.
   MongoDB's experience says generate-tests-from-spec beats retrofitted
   trace checking (2 wks & found a bug vs 10+ wks & found nothing).
2. **History checking** (Elle for isolation anomalies, Porcupine for
   linearizability): only needs request/response logs; no native migration
   concept — tag ops with schema version (open design point).
3. **Trace validation against the spec** (TLC trace checking, P/PObserve):
   the tight loop, but only viable if the spec is written trace-first;
   retrofitting fails.
4. **Deterministic simulation** (madsim/turmoil if Rust): strongest for
   migration-vs-request interleavings, replayable seeds.
5. **Code-level proofs** (note 03: Verus/Dafny with LLM assistance is the
   best-evidenced combo, 68–86% on benchmarks): reserve for small, hot,
   tricky functions the agent optimizes hardest — not whole handlers.

### D5 — Agent loop protocol

Findings (notes 02, 06): CEGIS shape is proven (Baldur, AlphaVerus, KaPilot):
LLM proposes, checker returns a concrete counterexample, LLM repairs.
Rules for our loop:
- Agent may edit **code**; the **spec is frozen** without human sign-off.
- Gate = conformance layer (D4) must stay green; objective (perf benchmark)
  is optimized only within that gate.
- The **counterexample-feedback payload** (violated invariant + trace +
  prior attempt) is a first-class interface reused at every layer.
- Vacuity/negative-test gate before any spec counts as "approved"
  (a spec that can't fail is a silent hole).
- Prefer oracles with crisp completeness stories (model checker verdicts,
  Elle cycle detection) over "N random runs found nothing".

## Candidate architectures

**A. Design-first (spec + model checker as oracle, MBT/history checking as
conformance).** Quint/TLA+ model of requests+migration; invariant oracle
(D2); Hypothesis/Elle conformance; no code proofs. Covers the whole brief;
weakest link is spec↔code fidelity (mitigated by generating tests from the
model). Lowest total cost.

**B. Proof-carrying code (verification-aware implementation).** Implement in
Rust+Verus (or Dafny compiled to Go/Java); invariants live in the code as
contracts; model checker only for the migration protocol. Strongest
guarantees and best LLM evidence per-function, but poor coverage of
system-level concurrency + DB state (the DB is outside the verified
boundary), slow verify cycles, and it locks the implementation language.

**C. Hybrid, layered (recommended).** A's design-level core, plus the typed
invariant schema front-end (D1) for developer authoring/review, plus
selective code-level proofs (B) only where the agent's optimizations are
riskiest. Start with A's components; the front-end and code proofs bolt on
without rework.

## Recommendation

Adopt **C**, built incrementally in this order:

1. **P1 — Migration model** (D3): Quint or PlusCal model of expand/contract
   with two app versions + concurrent requests, F1 element states, checked
   invariants ("no request observes an absent column", version-skew bound),
   JSON counterexamples. Serializable first; SI as a stretch.
2. **P2 — Invariant oracle** (D2): CLI, invariants in (typed schema →
   SMT), Z3 unsat cores + witness generation, Bedrock-style verdict
   taxonomy. Independent of P1's language choice.
3. **P3 — Conformance harness** (D4): toy Python API + Postgres + pgroll;
   Hypothesis stateful tests with a "run migration" rule; optionally dump
   Jepsen-style history through Elle. Empirically tests whether pgroll's
   dual-write actually preserves isolation (note 05 says nobody has checked).
4. **P4 — Agent-loop skeleton** (D5): generic `check → counterexample →
   LLM repair → recheck` CLI usable over P1's checker and P3's tests.

P1+P2 together demonstrate pipeline steps 1–4 end-to-end on paper;
P3 closes the loop to a real system; P4 is the reusable scaffold for M4.

## Open questions for the developer (M2)

- Target isolation level of the real system (READ COMMITTED vs SI vs
  SERIALIZABLE)? Determines the substrate spec for P1/P3.
- Implementation language of the example app — Python (fastest for P3) vs
  Rust (unlocks Stateright/madsim/Verus later)?
- Quint vs classic TLA+ for P1 (or do both on the same model as an A/B)?
- Is a restricted typed invariant schema acceptable as the primary
  developer-facing artifact, with the full model generated behind it?
