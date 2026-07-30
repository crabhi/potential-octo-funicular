# Synthesis: candidate architectures & recommendation

Date: 2026-07-30. Status: skeleton — tool choices to be filled in from notes 01–06.

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

Key design decisions (each has a section below once research lands):

- **D1 — spec language**: what the LLM writes and the developer reviews.
- **D2 — consistency oracle**: how "query for contradictions / unexpected
  outcomes" is implemented (unsat cores, instance enumeration, bounded
  traces as "did you expect this?" examples).
- **D3 — design-level concurrency model**: how requests interleave with
  migration steps; refinement path from serializable to concurrent.
- **D4 — spec↔code conformance**: the trust link that makes the green
  checkmark meaningful for the real system (trace validation, MBT,
  deductive proofs — likely layered).
- **D5 — agent loop protocol**: what the agent may change (code yes,
  spec no without human sign-off), what gates an edit, how counterexamples
  are rendered back into the agent's context.

## Non-negotiables noted from the brief

- Concurrency (parallel requests, migration during traffic) must be
  expressible; starting serializable is fine but the tools must not dead-end.
- Checker output must be machine-readable enough to feed an agent.
- Developer stays the authority on the spec; agent is the authority on code.

## Candidate architectures

(to be filled after notes 01–06 land)

- A. Design-first: spec language + model checker as design oracle, MBT/trace
  checking as conformance, no code-level proofs.
- B. Proof-carrying code: verification-aware implementation language
  (specs live in the code), model checker only for the migration protocol.
- C. Hybrid/layered: A for system-level invariants + selective code-level
  proofs for hot, tricky functions the agent optimizes hardest.

## Recommendation

(to be written)
