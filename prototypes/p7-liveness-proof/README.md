# Track M — completion as a liveness theorem (and a wrong prediction)

Random-trace witnesses ("`featDone` reached in 84% of traces") only
*suggest* the migration can complete. This track replaces that with
temporal proof: TLC checks `<>(phase = DONE)` over the **complete state
graph** of the protocol, under explicitly stated fairness assumptions.

Setup: `Migration.tla` is a lean port of the repaired protocol (P4's
`migration.qnt`, dirty-flag SI encoding; ghost read machinery dropped as
irrelevant to completion). TLC 1.7.4 (from nightly.tlapl.us; GitHub
releases are proxy-blocked here). Fairness: weak fairness on the migration
machinery and the rollout (`Expand`, `Upgrade`, backfill actions,
`SwitchRead`, contract steps) — **none on app writes**: the application
owes the migration nothing.

## Results (all complete-state-space, not sampling)

| Configuration | Property | Verdict |
|---|---|---|
| Unbounded app-write interference, full fairness | `<>(phase=DONE)` | **HOLDS** (623 states, exhaustive) |
| Write budget = 3, full fairness | `<>(phase=DONE)` | HOLDS |
| Full interference, fairness minus `Upgrade` (rollout stalls) | `<>(phase=DONE)` | **VIOLATED** — lasso: an instance never upgrades, drain never completes |

Safety (`ColumnsAgree`) checked alongside in every run: holds.

## The honest surprise

The track was designed expecting a **starvation counterexample**: adversarial
writes keep dirtying a row, every backfill attempt aborts, completion is
never guaranteed — the classic online-backfill starvation story, and the
reason the design brief said "prove it under a bounded-interference
assumption".

TLC refused to find one, and the reason is a real insight about the
repaired choreography: **backfill only runs after the drain, and after the
drain every application write is a dual-write** — so any write that aborts
a backfill attempt has *already synced the very row being copied*
(`N = O = v`). The backfill criterion `WHERE N IS DISTINCT FROM O` then
simply stops selecting that row. Interference doesn't starve the backfill;
it does the backfill's work. The classic starvation scenario requires
non-dual-writing interference — exactly what the drain gate excludes.

So the theorem is stronger than requested: *completion needs no
interference assumption at all*, only fairness of the migration machinery
and of the rollout itself. The negative control shows the rollout-fairness
assumption is genuinely load-bearing (drop it and TLC hands you the
stalled-deploy lasso), i.e. the only way this migration fails to complete
is operational: someone never finishes the deploy.

A prediction made by the (AI) protocol author was falsified by the
checker — in the favorable direction this time. Either direction, the tool
settles it; that is the point of this whole project.

## What this is and is not

- **Is**: a complete temporal proof for the fixed constants (2 keys, 2
  instances, 2 values) — every behavior of the finite model checked, no
  sampling, no step bound.
- **Is not**: parameterized (any-size) liveness — that composes Track J's
  approach with ranking arguments; future work.
- The Quint↔TLA+ port is hand-written and small (≈140 lines); its
  faithfulness to `migration.qnt` is trusted (reviewable side-by-side).

## Reproduce

```bash
curl -sfLO https://nightly.tlapl.us/dist/tla2tools.jar
java -cp tla2tools.jar tlc2.TLC -config unbounded.cfg -deadlock Migration.tla  # HOLDS
java -cp tla2tools.jar tlc2.TLC -config bounded.cfg   -deadlock Migration.tla  # HOLDS
java -cp tla2tools.jar tlc2.TLC -config norollout.cfg -deadlock Migration.tla  # lasso
```
