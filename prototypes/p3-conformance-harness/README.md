# P3 — Conformance harness

Empirical counterpart to the design-level notes in `research/05-db-migrations-concurrency.md`
and the pipeline sketched in `research/07-synthesis.md`. This is workflow
**step 4** ("The formal requirements are used to verify actual system
behavior... model-based testing") applied to a real system: a real Rust/axum
API backed by a real Postgres 16 database, a real expand/contract migration,
and a Python/Hypothesis harness that drives the real API concurrently with
the real migration and checks invariants.

No mocks. No Docker. Postgres runs natively.

## What it demonstrates

- An **expand/contract schema migration** (`users.name` -> `users.full_name`)
  decomposed into the F1-style steps described in note 05: expand, install a
  propagation trigger (the "write-only" analogue), backfill, flip the read
  switch, contract.
- **Version skew**: two instances of the same API binary run side by side —
  `APP_VERSION=1` (only ever knows about `name`) and `APP_VERSION=2` (schema
  migration-aware, checks a `migration_state` control table per request) —
  exactly the "two servers straddling old/new schema" scenario the F1 paper
  and note 05 formalize.
- A **Hypothesis `RuleBasedStateMachine`** (`harness/test_stateful.py`) that
  treats "advance the migration one step" as just another rule alongside
  create/update/read, and checks a sequential correctness invariant against
  the real HTTP API.
- A **concurrent load test** (`harness/test_concurrent.py`) that runs a
  thread pool of HTTP workers against both instances *while the real
  migration runs in a background thread*, then checks system-level
  invariants (no schema errors, no 5xx, final DB state consistent) and
  prints a summary table.
- One **genuine race we found and fixed** while building this (see
  "Findings" below) — the assignment explicitly treats that as a feature,
  not a distraction.

## Architecture

```
                         ┌────────────────────────┐
                         │   Postgres 16 (p3demo)  │
                         │  users(id, name[,full_  │
                         │  name]) + migration_    │
                         │  state(dual_write,      │
                         │  read_switch,contracted)│
                         └───────────┬─────────────┘
                    per-request flag check + SQL
             ┌───────────────────────┼───────────────────────┐
             │                       │                       │
   ┌─────────▼─────────┐   ┌─────────▼─────────┐             │
   │ p3_api APP_VERSION │   │ p3_api APP_VERSION │             │
   │   =1  (port 3001)  │   │   =2  (port 3002)  │             │
   │ only knows `name`  │   │ dual-write/switch  │             │
   └─────────▲──────────┘   └─────────▲──────────┘             │
             │  HTTP (create/read/update)                      │
   ┌─────────┴──────────────────────────────────────┐   migrate.py
   │        harness/ (Python, Hypothesis+pytest)     │   step-by-step,
   │  test_stateful.py   test_concurrent.py          │◄──run-all, or
   │  sequential model    concurrent thread pool +    │   driven by the
   │  RuleBasedStateMachine background MigrationRunner│   test harness
   └──────────────────────────────────────────────────┘
```

Migration state machine (per `migrate/migrate.py`, mirrors note 05's
`Absent -> WriteOnly -> Present -> DeleteOnly` element lifecycle, specialized
to this one-column rename):

```
v1-only --expand--> expand --install-trigger--> trigger-installed
   --backfill(loop)--> backfilled --read-switch--> read-switch
   --[drain v1, quiesce]--> contract --> contracted
```

- **expand**: `ALTER TABLE users ADD COLUMN full_name text` (nullable).
- **install-trigger**: a `BEFORE INSERT OR UPDATE` trigger sets
  `NEW.full_name := NEW.name` on *every* write, regardless of which app
  version issued it. This is what lets v1 (which never mentions
  `full_name`) keep working correctly all the way through backfill and
  read-switch — v1's writes are transparently propagated.
- **backfill**: `UPDATE users SET full_name = name WHERE full_name IS NULL
  ... LIMIT n`, looped, one transaction per batch. Because the trigger is
  already installed, this only ever has to touch rows that existed *before*
  the trigger went in; every row written after that point already has
  `full_name` set.
- **read-switch**: flips `migration_state.read_switch`; v2 starts reading
  `full_name` (v1 is unaffected — it never reads `full_name`).
- **contract**: drops the trigger/function, then drops `name`, in one
  transaction that also flips `dual_write=false, contracted=true`.

## Correspondence: harness invariants <-> note 05's formal invariants

| Harness check | note 05 / F1 formal counterpart |
|---|---|
| No request gets a 5xx or "column does not exist" (`test_stateful.py` rules, `test_concurrent_migration_with_drain`) | "No request observes a column that is gone" / no orphan-data or integrity anomaly |
| `read_user` asserts the returned name equals the model's expected current value, from either instance, at every migration phase | F1's core correctness property: every committed read is `SchemaCompatible(v, schemaState[e])` and returns the true current value — no orphan/integrity anomaly |
| Two API instances (v1, v2) running concurrently throughout | Version-skew bound `∀ i,j: |i.appVersion - j.appVersion| ≤ 1` — modeled directly by running exactly two versions side by side |
| `v1_drained` flag / draining-v1 phase, enforced before `contract` in both test files | "Contract only after drain: `migrationPhase=Contract ⇒ ∀ i: i.appVersion ≥ N+1`" — the ordering/liveness precondition note 05 calls out explicitly |
| `test_concurrent_migration_without_drain_demonstrates_anomaly` (deliberately skips the drain) | Empirical proof that the precondition is load-bearing: violate it and the orphan/integrity-anomaly-freedom guarantee breaks, exactly as F1's theorem predicts |
| Backfill runs as ordinary batched `UPDATE`s under Postgres's default isolation, not a special-cased bulk copy | "Backfill sees a consistent snapshot... backfill is just another transaction, not exempt from isolation" |
| `test_concurrent_migration_with_drain`'s final-state check (every user's DB value == last recorded write, checked only after quiescence) | Isolation preserved end-to-end: doesn't attempt to assert a total order on individual concurrent reads (that would need a real isolation checker — see Limitations), only that convergence holds once writes stop |

## How to run

Prerequisites (already satisfied in this environment): Postgres 16 present
(cluster started by the script), Rust/cargo, Python 3.

```bash
./run_demo.sh
```

This builds the API, starts Postgres if needed, provisions the `root`
role/`p3demo` database if needed, resets the schema, starts both instances,
runs the Hypothesis stateful suite then the concurrent suite (`pytest -s`,
so the summary tables print), and stops the instances afterward. It is
idempotent — re-run it any number of times.

To run pieces individually:

```bash
# schema / migration driver, usable standalone
harness/.venv/bin/python3 migrate/migrate.py reset
harness/.venv/bin/python3 migrate/migrate.py status
harness/.venv/bin/python3 migrate/migrate.py step expand
harness/.venv/bin/python3 migrate/migrate.py run-all --with-traffic-pause-ms 200

# harness, once both instances are running on 3001/3002
cd harness
.venv/bin/python3 -m pytest test_stateful.py -s -v
.venv/bin/python3 -m pytest test_concurrent.py -s -v
```

## Findings

**A real TOCTOU race in v2 itself, not just in v1.** The first version of
`test_concurrent_migration_with_drain` failed reproducibly:

```
error: ('draining-v1', 'v2', 'read', 500,
        "{'error': 'column \"name\" does not exist'}")
error: ('draining-v1', 'v2', 'update', 500,
        "{'error': 'column \"name\" of relation \"users\" does not exist'}")
```

The task brief predicted a lost-update race between the dual-write trigger
and backfill; that one did *not* materialize, and it's worth saying why: the
trigger always recomputes `full_name := NEW.name` from each write's own
current row image inside the *same* transaction as the write, so it is
atomic and idempotent by construction — there's only one source of truth
(`name`) until the read-switch flips, and mirroring it is convergent no
matter how backfill and concurrent writes interleave. The actual bug was
one level up, in the **app's own request handling**: v2 does a
check-then-act — `SELECT dual_write, read_switch, contracted FROM
migration_state` to decide which SQL text to build, then executes that SQL
a moment later. Those two steps are two separate round-trips, not one
transaction. If `contract` (which drops `name` and flips the flags,
atomically, in its own transaction) commits in the gap between a v2
request's flag-check and its query execution, that request has already
committed to SQL text referencing `name` — and gets a "column does not
exist" 500, indistinguishable from v1's own version-skew failure mode. This
is exactly the class of anomaly the F1 paper's lease protocol and ≤1
version-skew invariant exist to bound, just showing up inside a single
"modern" instance instead of between two versions.

**Fix applied**: a brief global quiesce (~150ms) of *all* traffic — not just
v1 — around the exact instant `contract` commits (see
`MigrationRunner.v2_allowed()` / the `quiescing` phase in
`harness/test_concurrent.py`, and the longer `draining-v1` window before
it). This mirrors the short atomic-cutover pause real online-DDL tools
(gh-ost, pt-online-schema-change) take during their final rename step, and
it isn't specific to this toy — any app that snapshots `migration_state`
outside its actual DML transaction has the same exposure at the last
cutover step. After the fix, `test_concurrent_migration_with_drain` is
consistently green across repeated runs (verified by hand and via
`run_demo.sh` run twice in a row, ~700-900 requests each run, 0 errors, all
final-state checks passing).

**`test_concurrent_migration_without_drain_demonstrates_anomaly` reliably
reproduces the anomaly** (typically 50+ `column ... does not exist` errors
per run) when v1 is deliberately *not* drained before contract — confirming
that the drain-before-contract precondition in note 05 is genuinely
necessary, not decorative. Interestingly this run's traffic tagged as phase
`read-switch` also shows a handful of errors: because there's no drain
pause in this mode, `contract` starts almost immediately (~0.15s) after
`read-switch`, so some requests tagged with the pre-contract phase still
straddle the cutover — the same underlying race as above, just visible in
a different bucket.

## Limitations / next steps

- **No Elle integration yet.** research/05 and 07-synthesis.md's D4 layer
  both suggest a Jepsen/Elle-style history check (Adya-anomaly detection
  from black-box operation logs, extended with schema-version tags) as the
  next rung above model-based testing. This harness records enough
  information (phase, app version, op, status, per-op timestamps implicit
  in `results`) to build an Elle-compatible history, but doesn't yet check
  it for G0/G1/G-single/G2-style anomalies — only the schema-transition and
  final-convergence invariants above. That's the natural next prototype.
- **Per-request `migration_state` polling is a toy simplification.** A real
  system would cache flags with a short TTL or push updates; the harness
  found a bug *because* of the naive per-request check, which is a feature
  for this exercise but would need re-verifying against whatever caching
  strategy a real implementation used.
- **Concurrency model is thread-pool + HTTP, not a deterministic simulator.**
  D4 in 07-synthesis.md ranks deterministic simulation (madsim/turmoil) as
  stronger for migration-vs-request interleavings, with replayable seeds.
  This harness's races are real but not reproducible-on-demand the way a
  seeded simulation's would be; the race documented above was found by
  running the suite, not by construction.
- **Only tests the one-column-rename migration.** The trigger-based
  propagation strategy is provably safe here because there's a single
  source of truth being mirrored; a harder migration (splitting a column,
  a derived/computed value, a uniqueness constraint) would need a different
  argument and might not enjoy the same "trigger makes it atomic" property.
- **Isolation level is Postgres's default (READ COMMITTED)**, not
  snapshot isolation as the project brief's M2 decision specifies for the
  formal model (P1). This prototype doesn't attempt to distinguish RC- vs
  SI-specific anomalies (write skew, etc.) — that's squarely P1's job on
  the model side; P3 only checks the schema-versioning invariants
  empirically, per D3/D4's "separable concerns" argument in
  07-synthesis.md.
