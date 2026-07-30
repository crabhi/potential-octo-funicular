# Track C — model-based test generation

Scoreboard row: **C | Model-based test generation | The generation
direction (spec drives app) catches implementation divergence cheaper than
trace checking (MongoDB's finding) | Mapping model actions→HTTP is too
lossy to give a trustworthy verdict | see verdict below**

See `../../../research/09-bridging-the-gap.md` for the full scoreboard.
This directory does not read or modify anything under `../app/` — it only
drives the app's existing HTTP server as a black box.

## Technique

1. **Generate**: `quint run ../model/cms.qnt --main cms_live --mbt
   --out-itf ... --n-traces 20 --max-steps 12` produces 20 ITF-JSON traces.
   The `--mbt` flag adds two fields to every state: `mbt::actionTaken` (the
   action name that produced this state) and `mbt::nondetPicks` (the exact
   `nondet` choices the simulator made to fire it, e.g.
   `{u: Some(1), a: Some(2)}`).
2. **Replay**: `adapter.py` decodes each trace, restarts the real
   Rust/axum server fresh (in-memory state, no reset endpoint) per trace,
   brings it to the model's `init` state, then walks the trace turning
   each step into exactly one HTTP call.
3. **Compare**: after each call the adapter asserts (a) the app returned
   2xx — acceptance parity — and (b) `GET /articles/:id` shows the article
   in the state the model's `artState` says it should be in — observable
   state parity.
4. **Divergence demo**: a second leg generates a handful of `cms_cached`
   counterexample traces (`--invariant invNoUnauthorizedActions`, which
   makes `quint run` stop right at the stale-session violation) and
   replays them against the app running `AUTH_MODE=live`, to show the live
   app's re-authorization catches exactly what the cached-semantics model
   let through.

## Model ↔ app correspondence (the part that took the actual work)

| Model | App | Resolution |
|---|---|---|
| `USERS = {1, 2}`, `ALICE=1` (author), `EVE=2` (editor) | seeded users `alice` (author), `bob` (author), `eve` (editor), `root` (admin) | Identity map `{1: "alice", 2: "eve"}`. No user setup needed — the model's two users already exist with matching roles. `bob`/`root` are simply outside the model's user set; `root` is used only as the bookkeeping admin token for demote/deactivate calls, which the model doesn't attach to any acting user either. |
| `ARTICLES = {1, 2}`, both DRAFT, both authored by `ALICE`, in `init` | app seeds 4 articles (`published`/`draft`/`in_review`/`archived`, mixed authors) — **not** the model's `init` | The app's seed state does *not* match the model's `init`. Setup phase: log in as alice, `POST /articles` twice, and map model article ids `1, 2` to the two freshly-created app ids. This is exactly the "if the app doesn't start with zero articles, do setup calls first" case the brief anticipated — except the app doesn't start at *zero* articles either, it starts with 4 unrelated ones, so setup can't just be "create 2 more" naively; it has to be paired with *only ever addressing the 2 new ones* for the rest of the replay. |
| `DRAFT/IN_REVIEW/PUBLISHED = 0/1/2` | `"draft"/"in_review"/"published"` | Direct int→string table. |
| `adminDemote`/`adminDeactivate` (no acting user in the model) | `POST /admin/{demote,deactivate}/:user`, requires an admin bearer token | Login as `root` once during setup (not a replayed model step) and use that token for every admin call in every trace. |
| `mbt::nondetPicks.u`, `.a` | the acting user / article for a step | Used directly. **This is what made action-argument recovery a non-issue** — see "what was painful" below. |

## Actual results

Environment: quint 0.32.0, Rust server built via `cargo build`/`cargo run`
against `../app/server/Cargo.toml`, Python via `../app/harness/.venv`
(reused, no new venv needed), server on port 3300, three consecutive full
runs of `./run_mbt.sh`.

### Leg 1 — live-vs-cms_live parity (the main claim)

| Metric | Value |
|---|---|
| Traces generated | 20 (`--main cms_live --mbt --max-steps 12`) |
| Trace length | every trace hit the step cap: 12 steps / 13 states (min=max=avg=13 states) |
| Traces replayed against real app (`AUTH_MODE=live`) | 20 / 20 |
| Steps executed | 240 |
| Steps rejected by the app | **0** |
| Observable state mismatches | **0** |
| Parity verdict | **PASS** — the app accepted every action the model's transition succeeded on, and every article's `draft`/`in_review`/`published` state matched the model's `artState` after every `submitReview`/`publish` step, across all 240 steps. |

This ran 3 times back to back with identical results (fresh server per
trace, clean teardown, port released between runs — verified by polling
`/health` until refused and confirming no `cms-server` process survives
`run_mbt.sh`).

### Leg 2 — divergence demo (cms_cached race traces → live app)

Direction implemented, and why (see `divergence_demo.py`'s docstring for
the full reasoning): replaying a `cms_live` trace onto a `cached`-mode app
predicts *no* divergence by construction (`cms_live` never contains an
action the live policy would forbid, and cached mode is only ever *more*
permissive than live, never less — so that direction is true but
uninteresting and can't exercise the actual bug class). The meaningful
direction is the other way: generate `cms_cached` traces that *do* contain
a step where the cached-semantics model permits an action the live policy
forbids (`lastActionOk` flips `true → false`), and replay that step
against the **live** app to see whether live re-authorization actually
catches it.

| Metric | Value |
|---|---|
| Race traces generated | 6 (`--main cms_cached --mbt --invariant invNoUnauthorizedActions`, one `quint run` invocation per trace since it halts at the first violation) |
| Divergence point found per trace | 6 / 6 (every trace ends exactly at a `submitReview` by a user cached as active but actually deactivated) |
| Live app rejected the divergent step (403 `inv_deactivated_does_nothing`) | **6 / 6 — CONFIRMED** |
| Live app silently accepted it (would be a real vulnerability) | 0 / 6 |

Sample output:

```
[CONFIRMED]  race_1.itf.json: step 3 (submitReview u=1 a=2) -- cms_cached
model allowed this (lastActionOk: true->false) but the LIVE APP REJECTED
IT (HTTP 403 inv_deactivated_does_nothing). Live re-authorization catches
exactly what the cached-semantics model missed.
```

All 6 generated race traces happened to land on the "deactivate alice,
then she submits for review anyway" variant rather than the
"demote eve, then she publishes anyway" variant — both are legal
counterexamples to `invNoUnauthorizedActions`, `quint run`'s random search
just found the same shape 6/6 times at `--max-steps 12`. The mechanism
covers both (`do_step` handles `publish` identically to `submitReview`);
this is a coverage note, not a limitation of the adapter.

## What was painful (and what wasn't)

- **Action-argument recovery was a non-issue, not because it's easy in
  general, but because `--mbt` handed it to us for free.** The brief
  anticipated needing to diff consecutive states to recover which
  user/article an action touched. `mbt::nondetPicks` made that
  unnecessary here — every step already carries `{u: Some(1), a: Some(2)}`
  and the adapter just reads it. Diffing would still be needed for a model
  with implicit/derived choices (e.g. an action that computes an argument
  rather than picking it `nondet`), which this model doesn't have. Verdict
  on the falsifier "mapping model actions→HTTP is too lossy": for *this*
  model, `--mbt` makes the mapping direct and lossless enough to trust.
- **The real friction was init-state reconciliation, not action mapping.**
  The model's `init` (2 fresh draft articles, both by alice) and the app's
  actual seed (4 articles, mixed authors/states, plus users the model
  doesn't know about) don't match, and there is no reset endpoint. This
  needed a whole setup phase (create articles, remap ids) that has nothing
  to do with the trace format — it's a property of this being a *shared,
  pre-seeded, stateful* real system rather than a blank slate. Any
  MBT-against-a-real-app effort will hit this; it's worth calling out
  explicitly rather than letting it hide inside "adapter code."
- **Namespacing in the ITF output** (`cms_live::cms::artState` vs
  `cms_cached::cms::artState`, depending on `--main`) meant variable names
  couldn't be hardcoded; `adapter.var_key()` does a suffix match instead.
  Minor, but would silently break on a naive port from one `--main` to the
  other.
- **Restarting the server per trace was the only viable state-reset
  strategy** (confirmed by `../app/README.md`'s own findings for the
  Python harness) — `cargo run` per trace adds real wall-clock cost (a
  few seconds of process spin-up × 26 traces) but it's the only way to get
  a trace's replay to start from a state the model's `init` can actually
  match.
- **The ITF value encoding required a small but easy-to-get-wrong decoder**
  (`#bigint`, `#map`, `#tup`, and the `{tag, value}` Option encoding, plus
  generic Quint records that are none of those and need field-wise
  recursion — this last case wasn't obvious from the format docs and only
  showed up as a `TypeError: unhashable type: 'dict'` on the first real
  run, from `mbt::nondetPicks` itself being an un-annotated record).

## Verdict

**Worked.** For this model/app pair, `--mbt` metadata makes model-based
test generation practical: 20/20 traces and 240/240 steps replayed with
full acceptance and state parity against the live app, and the divergence
demo cleanly reproduces the conformance signal Track C exists to find (6/6
`cms_cached` race traces confirmed rejected by live re-authorization,
0/6 silent vulnerabilities). The technique's real cost center wasn't
"mapping model actions→HTTP" (the falsifier this track was built to test)
— `nondetPicks` defeats that falsifier directly for models that pick
arguments `nondet`. The real cost was **reconciling a stateful, pre-seeded
real system's initial state with the model's `init`**, which is a
setup-phase problem specific to testing against a shared/seeded backend,
not a weakness of the generation-direction technique itself. Needs X: a
model whose actions compute arguments rather than picking them `nondet`
(no `--mbt` picks to read), to see whether the diffing fallback the brief
originally proposed is still needed elsewhere in this codebase.

## Layout

```
mbt/
  adapter.py           ITF decoding, model<->app mapping, server lifecycle,
                        single-step replay (do_step), full-trace replay
  replay_live.py        leg 1: cms_live traces -> live app, scoreboard, exit code
  divergence_demo.py    leg 2: cms_cached race traces -> live app, divergence demo
  run_mbt.sh             generates traces, runs both legs, prints summary
  traces/live/           20 cms_live ITF traces (regenerated each run)
  traces/cached/         cms_cached race-counterexample ITF traces (regenerated each run)
```

## How to run

```bash
cd examples/cms/mbt
./run_mbt.sh
```

Builds the server once, generates fresh traces, replays both legs, prints
the scoreboard, and exits non-zero iff the live-vs-cms_live parity leg
(leg 1) had a rejected step or state mismatch. Idempotent and
self-cleaning: each trace gets its own freshly spawned `cms-server`
process (`cargo run` under the hood, per the harness convention in
`../app/`), and `run_mbt.sh` kills everything it started — including a
best-effort `pkill -f cms-server` — on exit via a `trap`. Override
`MBT_PORT`, `N_LIVE_TRACES`, `N_CACHED_RACE_TRACES`, or `MAX_STEPS` via env
vars if needed.
