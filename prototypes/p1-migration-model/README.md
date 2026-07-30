# P1: Quint model — online schema migration concurrent with API requests

A formal model (Quint, TLA+ semantics) of the project's core scenario:
an expand/contract column rename (`name` → `full_name`) executed **while two
app instances serve concurrent reads and writes**, under snapshot isolation.

This is pipeline step 4 of the brief (model check the design) and doubles as
a worked example for step 3 (the checker surfacing "unexpected outcomes").

## Prerequisites & quickstart

```bash
npm install -g @informalsystems/quint   # Quint CLI (>= 0.32)
./check.sh                              # typecheck + simulate + verify, both configs
```

`quint verify` needs a JVM (Apalache is fetched automatically on first use).
If the Rust simulator backend can't be downloaded in your environment, the
scripts already pass `--backend typescript`, which needs nothing extra.

## What is modeled

- **F1-style column states** (`Absent → WriteOnly → Present`,
  `Present → DeleteOnly → Absent`) per Rae et al., VLDB 2013 (research note 05).
- **Migration phases**: expand → (rolling upgrade + backfill) → read switch →
  contract.
- **Two app versions**: v1 writes only the old column; v2 dual-writes and
  reads the new column after the switch. Rolling upgrade is nondeterministic.
- **Snapshot isolation**: app requests are single-statement (their snapshot
  is trivially atomic). The backfill is the real multi-step SI transaction:
  it snapshots a row (value + row version) and commits later with
  first-committer-wins conflict detection at row granularity — the Postgres
  REPEATABLE READ behavior.
- **Ghost state**: `logical` (the value the application believes each key
  holds) and `lastReadOk` (falsified when any read returns a stale value).

Invariants checked (`invAll`):
- **I1 `invReadsCorrect`** — no committed read ever returns anything but the
  current logical value.
- **I2 `invColumnsAgree`** — after the read switch, while both columns live,
  they agree (F1 "no integrity anomaly" for a rename).
- **I3 `invBackfillDoneAtSwitch`** — reads never switch before every row has
  a new-column value.

Two instantiations of the same module:
- `correct` — `DRAIN_GUARD = true`: backfill start **and** read switch wait
  until every instance runs v2.
- `broken` — `DRAIN_GUARD = false`: no drain coordination.

## Results

```
quint run    --main correct  --invariant invAll   # no violation, 30k traces
quint run    --main broken   --invariant invAll   # violation in <1s
quint verify --main correct  --invariant invAll --max-steps 12   # NoError (Apalache, symbolic)
quint verify --main broken   --invariant invAll --max-steps 12   # counterexample in ~10s
```

Run `./check.sh` to reproduce all of it.

## The interesting part: the checker broke my "correct" protocol twice

This model was written by an (AI) engineer who believed each version was
correct. The checker disagreed twice, and both counterexamples correspond to
real production failure modes:

1. **Drain guarded only at backfill start.** First version required "all
   instances v2" only before backfill. Counterexample: v2 dual-writes fill
   the new column for every key, so the read switch's "backfill complete"
   condition is satisfied **without any backfill running** — while a v1
   instance is still alive. It then writes the old column post-switch and a
   v2 reader returns a stale value. Fix: the drain condition must gate the
   read switch too.

2. **`WHERE full_name IS NULL` backfill is wrong under rolling deploys.**
   Second version backfilled only keys with no new-column value.
   Counterexample: during the rolling window, a v2 instance dual-writes key
   k (N now non-NULL), then a still-live v1 instance overwrites the old
   column only. N is non-NULL but **stale**, the IS-NULL backfill never
   revisits it, and the staleness survives the drain and the switch. Fix:
   backfill `WHERE new IS DISTINCT FROM old` (re-copy out-of-sync rows) and
   gate the switch on "all rows in sync", not "all rows non-NULL".

Both bugs were found by random simulation in under a second and confirmed
by Apalache symbolically; both fixes are annotated with NOTE comments in
`migration.qnt`. This is exactly the workflow the project proposes: the
developer states invariants (I1–I3 are one-liners), and the reasoning engine
finds the non-obvious protocol consequences.

Note also what the *broken* config demonstrates for pgroll (note 05): pgroll
avoids the v1-doesn't-dual-write problem by installing **database triggers**
that dual-write on behalf of all clients — the model shows why app-level
dual-writing alone genuinely needs the drain choreography.

## Simplifications / next steps

- Values are small ints; NULL is `-1`; two keys, two instances, two values —
  enough for the anomalies, tiny enough for fast checking.
- Row-granularity write conflicts (Postgres-like). A column-granularity
  variant would surface additional backfill-vs-write races — worth a toggle.
- App transactions are single-statement; multi-statement app transactions
  (read-then-write under one snapshot) would enable write-skew-style
  anomalies interacting with migration — the natural extension for testing
  SI-specific behavior (research note 05's anomaly catalogue).
- Liveness (the migration eventually completes) is not checked, only safety.
- Machine-readable counterexamples: `quint run --out-itf trace.itf.json`
  works and is the intended input for the future agent loop (P4).
