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
 agent loop: LLM edits code freely; the spec is frozen; counterexamples
 flow back as the repair signal                              (P4, P5 — done)
```

**Start here if you want to learn the method**: `docs/manual.md` — the
field manual. One compound document teaching all three layers (rules as
the program, models before code, the frozen gate + agent loop) and how
they compose, with every example runnable from this repository.

## Repository map

| Path | What | One-command entry |
|------|------|-------------------|
| `docs/manual.md` | **The field manual**: the whole method in one teaching document — three layers, composition, honest costs | — |
| `research/INDEX.md` | Index of all research notes (start here for the why) | — |
| `research/07-synthesis.md` | Candidate architectures, decisions D1–D5 | — |
| `research/08-workflow-vision.md` | The holistic workflow & what's novel | — |
| `prototypes/p1-migration-model/` | Quint model: online migration + concurrent requests under snapshot isolation | `./check.sh` |
| `prototypes/p2-invariant-oracle/` | Z3 oracle: contradictions, witnesses, vacuity, claim verdicts | `./demo.sh` |
| `prototypes/p3-conformance-harness/` | Rust API ×2 versions + Postgres + live migration under concurrent load | `./run_demo.sh` |
| `examples/cms/` | **Worked example**: a CMS (roles, drafts, public access) guarded by the full pipeline — rules → oracle → model → real app | see its README |
| `examples/rule-driven-cms/` | **Worked example, inverted framing**: the whole CMS ground-up as a rule base executed by a generic engine; Z3 analyzes the rules themselves (research note 13) | `./check.sh` |
| `examples/taskboard/` | **End-to-end application**: Flowdeck, a multi-tenant team kanban SaaS on the generic reflected UI — 7 tickets → 150 lines of rules, zero app-specific code; honest developer-experience journal (research note 14) | `./check.sh`, `python app.py` |
| `examples/helpdesk/` | **The guardrail-10 + multi-entity prototype**: Relay, a customer-support desk whose htmx UI is hand-written and FREE while every interaction is decided inside a verified kernel API; three ruled entity types in one rule base (case, comment, attachment) with context-sensitive child rules — the kernel joins the parent, never the client; boundary held by lint; research notes 15 + 16 | `./check.sh`, `python app.py` |
| `examples/approvals/` | **The manual's worked example**: Clearance, a miniature expense-claims service built line by line in `docs/manual.md` Part 1 — 10 rules, 3,456 situations, the gate in all three directions, and the round-1 draft the gate must keep failing | `./check.sh` |

## Prerequisites

- **P1**: Node (`npm i -g @informalsystems/quint`); JVM for `quint verify`.
- **P2**: Python 3.11+ (`demo.sh` bootstraps its own venv).
- **P3**: Rust/cargo, Python 3, local Postgres 16 (`run_demo.sh` starts the
  cluster and bootstraps everything else).

## Status

M1 (research), M2 (decisions), M3 (prototypes) and M4 (the closed agent
loop: repair tracks A/F, optimization track H, proof escalation tracks
I–M) are done. Current phase: the rule-driven method as the programming
surface — six services on one generic engine, the kernel boundary, and
the field manual (`docs/manual.md`). See `research/00-project-brief.md`
for the living plan and `research/INDEX.md` for the change log.
