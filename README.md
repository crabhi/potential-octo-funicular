# Formal proofs as guardrails for LLM agents

Research project exploring a **novel workflow for developing large-scale
systems**: the developer authors *intent* as formal invariants, LLM agents
author and optimize the *implementation*, and reasoning engines (SMT solvers,
model checkers, conformance harnesses) arbitrate between them. Code becomes
cheap to regenerate; the spec becomes the durable artifact.

The studied system model: a web application whose future state depends only
on (possibly concurrent) API requests and database migrations that run
**while the application serves traffic** — the classic hard case for
correctness at scale, and one where the model checker has already
falsified two protocol designs a careful engineer believed correct
(see `prototypes/p1-migration-model/README.md`).

## The workflow

```
 developer intent (NL invariants)
        │  LLM translates, developer reviews (grounded, sentence-by-sentence)
        ▼
 typed invariant layer  ──►  reasoning engine: contradictions? vacuous?
        │                    surprising-but-allowed states?          (P2)
        ▼
 temporal/concurrency model (Quint)  ──►  model checking of the design (P1)
        │
        ▼
 conformance layer: the spec exercises the REAL system                (P3)
        │
        ▼
 agent optimization loop: LLM edits code freely; the spec is frozen;
 counterexamples flow back as the repair signal                (P4, planned)
```

## Repository map

| Path | What | One-command entry |
|------|------|-------------------|
| `research/INDEX.md` | Index of all research notes (start here for the why) | — |
| `research/07-synthesis.md` | Candidate architectures, decisions D1–D5 | — |
| `research/08-workflow-vision.md` | The holistic workflow & what's novel | — |
| `prototypes/p1-migration-model/` | Quint model: online migration + concurrent requests under snapshot isolation | `./check.sh` |
| `prototypes/p2-invariant-oracle/` | Z3 oracle: contradictions, witnesses, vacuity, claim verdicts | `./demo.sh` |
| `prototypes/p3-conformance-harness/` | Rust API ×2 versions + Postgres + live migration under concurrent load | `./run_demo.sh` |
| `examples/cms/` | **Worked example**: a CMS (roles, drafts, public access) guarded by the full pipeline — rules → oracle → model → real app | see its README |
| `examples/rule-driven-cms/` | **Worked example, inverted framing**: the whole CMS ground-up as a rule base executed by a generic engine; Z3 analyzes the rules themselves (research note 13) | `./check.sh` |

## Prerequisites

- **P1**: Node (`npm i -g @informalsystems/quint`); JVM for `quint verify`.
- **P2**: Python 3.11+ (`demo.sh` bootstraps its own venv).
- **P3**: Rust/cargo, Python 3, local Postgres 16 (`run_demo.sh` starts the
  cluster and bootstraps everything else).

## Status

M1 (research), M2 (decisions) and M3 (prototypes) are done; M4 — the closed
agent loop where an LLM optimizes code against a frozen formal gate — is the
next milestone. See `research/00-project-brief.md` for the living plan.
