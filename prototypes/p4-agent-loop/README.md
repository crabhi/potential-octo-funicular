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

(recorded below as they are run)
