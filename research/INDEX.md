# Research notes index

Keep this file current: one line per note, newest changes noted in the log.

| File | Topic | Status |
|------|-------|--------|
| [00-project-brief.md](00-project-brief.md) | Problem statement, system model, milestones | living |
| [01-spec-languages.md](01-spec-languages.md) | Specification languages & model checkers (TLA+, Quint, Alloy, P, ...) | draft |
| [02-runtime-verification.md](02-runtime-verification.md) | Runtime verification, trace checking, consistency checkers | draft |
| [03-code-level-verification.md](03-code-level-verification.md) | In-language verifiers (Verus, Dafny, KeY, Gobra, Nagini, ...) | draft |
| [04-reasoning-engines.md](04-reasoning-engines.md) | SMT solvers & querying invariants for contradictions | draft |
| [05-db-migrations-concurrency.md](05-db-migrations-concurrency.md) | Formalizing online schema migrations + concurrent requests | draft |
| [06-llm-formal-methods.md](06-llm-formal-methods.md) | LLM x formal methods: spec synthesis, verified codegen, agent loops | draft |
| [07-synthesis.md](07-synthesis.md) | Cross-cutting synthesis: candidate architectures & recommendation | draft |
| [08-workflow-vision.md](08-workflow-vision.md) | Holistic workflow: roles, contract, novelty, adoption path | draft |
| [09-bridging-the-gap.md](09-bridging-the-gap.md) | M4 phase log: five bridge tracks, scoreboard, episode results | living |

Worked examples live under `examples/` (currently: `examples/cms/` — a CMS
guarded by the full pipeline; its README is the workflow narrative).

## Change log

- 2026-07-30 (M4 phase 2, "strong guarantees over NL guidance"): Track F —
  gate-strengthened repair loop forces the full fix in 1 round with an
  unchanged generic prompt (controlled comparison vs episode 1); Track G —
  authorization kernel boundary is now a compile error (Grant<Op> capability
  tokens), harness and proofs unchanged. See 09-bridging-the-gap.md.

- 2026-07-30 (M4 phase 1): five bridge tracks executed in parallel — A repair
  loop WORKED (1 round, exposed safety-only-gate liveness gap), B trace
  validation WORKED, C model-based testing WORKED (240/240 parity, 6/6
  divergences), D Dafny proven-kernel-to-Go WORKED, E Kani spike: exhaustive
  wins at finite domains, Kani at unbounded — see 09-bridging-the-gap.md.

- 2026-07-30: repo created; brief written; research agents dispatched for notes 01–06.
- 2026-07-30: 06-llm-formal-methods.md drafted.
- 2026-07-30: 05-db-migrations-concurrency.md drafted.
- 2026-07-30: all six research notes (01–06) drafted; 07-synthesis.md written with candidate architectures A/B/C, recommendation (hybrid C), and proposed prototypes P1–P4. Awaiting developer decision (M2).
- 2026-07-30: M2 decided — P1+P2+P3, Quint, Rust app, snapshot isolation (see 00-project-brief.md Decisions). Prototype work started under prototypes/.
- 2026-07-30: P1 done (prototypes/p1-migration-model/) — Quint model of expand/contract + concurrent requests under SI. The checker falsified two successive "correct" protocol versions (drain guard only at backfill; IS NULL backfill criterion) before the third passed simulation + Apalache. See P1 README.
- 2026-07-30: P2 done (prototypes/p2-invariant-oracle/) — Z3-backed CLI: check/witness/vacuity/claim with unsat cores and Bedrock-style verdicts; 15 tests green.
- 2026-07-30: ease-of-use pass — root README (repo entry point), P2 demo.sh, P1 prerequisites section; 08-workflow-vision.md added (holistic framing for slides/review).
- 2026-07-30: P3 done (prototypes/p3-conformance-harness/) — Rust axum API x2 versions + Postgres + trigger-based expand/contract migration under concurrent load; found & fixed a real TOCTOU race at contract cutover; negative test reproduces the no-drain anomaly (59 errors/run). M3 complete.
