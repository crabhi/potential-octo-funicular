# P4 — the closed repair loop

The keystone of the workflow (research/07 D5): a checker finds a
counterexample, an LLM repairs the artifact, the checker re-judges — fully
automated, with the spec **mechanically frozen** so the agent can only fix
the protocol, never weaken the ruler it is measured by.

```
        ┌───────────────┐   counterexample (ITF JSON)   ┌──────────────────┐
        │ Quint checker │ ────────────────────────────► │ headless claude  │
        │ (30k traces + │                               │ -p, weaker model │
        │  Apalache)    │ ◄──────────────────────────── │ (Read/Edit only) │
        └───────────────┘        minimal protocol edit  └──────────────────┘
                 frozen invariant section: any edit reverted, round failed
```

## Testbed

`protocol/migration.qnt` — the expand/contract migration protocol from P1,
with drain guards in place but **one seeded flaw**: the backfill uses the
textbook `WHERE new IS NULL` criterion (and the switch checks only
non-NULL-ness). This is P1's "bug #2" — a real production failure mode that
random simulation catches in seconds and whose correct fix needs *two
coupled edits* (re-copy out-of-sync rows; gate the switch on all rows
agreeing), making it a fair, non-trivial repair task.

## Harness (`loop.py`)

- `quint typecheck` + `quint run` (30k traces); on violation, the trace is
  exported as ITF JSON, trimmed, and embedded in the repair prompt together
  with a domain explanation and the rules of engagement.
- Repairer: `claude -p --model sonnet --permission-mode acceptEdits
  --allowedTools Read,Edit` — deliberately a **weaker model**; the gate, not
  the model, carries the correctness burden.
- Spec freeze: the invariant section is diffed after every round; any
  change reverts the whole round (`failed_spec_edit`).
- `--verify`: after the loop goes green on simulation, Apalache
  symbolically verifies (12 steps); a verify failure keeps the loop going.
- Every round logged under `episodes/<ep>/round-<k>/` (prompt, agent
  output, resulting file, checker verdict) — the episode is auditable.

## Usage

```bash
python3 loop.py --model sonnet --rounds 4 --verify
```

## Episode results

### ep-20260730-172415 — model: sonnet, seeded bug: IS-NULL backfill

```
round 1: violation found, dispatching repairer (sonnet)
round 2: GREEN (no violation in 30000 traces)
  apalache verify: NoError
loop finished: protocol repaired
```

**The loop worked** — one repair round, no spec edits attempted, green on
30k random traces and symbolic verification to 12 steps.

**And the fine print is the most valuable finding.** The repairer changed
only the read-switch guard (`dbN != NULL` → `dbN == dbO`, with a correct
explanatory comment) and left the backfill criterion at `WHERE N IS NULL`.
That fix is *sound*: with the switch gated on all rows agreeing, no stale
value can ever be read — every safety invariant holds, and Apalache
confirms it. But it is *partial*: a row whose N went stale before the
drain is never re-copied (backfill only touches NULL rows) and now blocks
the switch **forever** unless some later write happens to touch that row.
The migration is safe but no longer guaranteed to complete.

The safety-only gate accepted a fix that traded away liveness — precisely
the failure mode predicted in `research/08` ("the safest system does
nothing") and in the CMS features work. The checker did its job; the gate
was underspecified. Lesson, now demonstrated empirically inside the loop:
**repair gates need liveness/feature properties alongside safety**
(here: "the migration can always still complete", a temporal property
under fairness — Quint/Apalache support temporal checking; wiring it into
the loop is the next iteration of this prototype).
