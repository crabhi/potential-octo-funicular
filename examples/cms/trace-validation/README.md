# Trace validation (Track B)

Track B of `research/09-bridging-the-gap.md`. Hypothesis: **client-side
action logs suffice to catch the cached-auth conformance violation from
outside the app** — i.e. without instrumenting the server, without a
special test mode, just by watching what a client saw the app do.

## What trace validation is

Drive the real running app like a normal client would, over plain HTTP,
and keep a log of exactly which actions it accepted (2xx). Then compile
that log — mechanically, one line of log to one line of Quint — into a
concrete `run` against the *real* formal model (`../model/cms.qnt`), and
ask the model checker one question: "does this exact sequence of committed
actions ever violate the model's own security ghost variable
(`lastActionOk`)?" If `quint test` passes, the sequence the app actually
executed was legal by the model's canonical, live-policy semantics. If it
fails, the app did something the model considers illegal — a real
conformance violation, demonstrated with the app's own accepted responses,
not a hypothetical one.

This is complementary to, and much cheaper than, model-based test
generation (Track C): it doesn't require mapping every model action to an
HTTP call in the generation direction, only in the reverse (log -> run)
direction, and it only needs to express the *specific* trace that actually
happened, not the whole action space.

## How the generated-run technique works

1. `driver.py` logs into the app as alice/eve (the model's fixed 2-user
   universe: alice=1=author, eve=2=editor), creates the model's two
   articles as setup (not logged — the model's `init` already has both
   articles as drafts by alice, so creation is plumbing, not a model
   action), then drives one scripted scenario, logging every 2xx response
   as `{"action": ..., "args": ...}` and every 403 separately (403s are
   dropped from the replay set — the model only models actions that
   *commit*; a rejection is a no-op on the model side).
2. `log2run.py` turns the `accepted` list into a Quint module that always
   imports the model at `CHECK_AT_ACTION = true` — the canonical, ground-
   truth policy — and chains one `.then(<action>(<args>))` per logged
   entry onto `init`, ending in a single `.expect(lastActionOk)`:

   ```qnt
   import cms(CHECK_AT_ACTION = true).* from "../model/cms"

   run traceReplayTest = init
     .then(loginU(1))
     .then(submitReviewU(1, 1))
     .then(loginU(2))
     .then(publishU(2, 1))
     .expect(lastActionOk)
   ```

3. `quint test generated_trace_*.qnt --backend typescript` either finds a
   run through that exact sequence ending with `lastActionOk` true (PASS —
   legal), or reports that it `Cannot continue to "expect"` because some
   `.then()` step's guard doesn't hold under the live policy (FAIL — the
   model refuses a step the app actually let through).

Always compiling against `CHECK_AT_ACTION = true` (not whatever mode the
app happened to be running in) is the point: the app's `AUTH_MODE=cached`
is exactly the thing under test for conformance to the canonical model, so
the reference has to be the live/ground-truth model, not a copy of the
app's own (possibly buggy) trust assumption.

Admin actions (`adminDemote`/`adminDeactivate`) are compiled as bare nondet
actions (`.then(adminDemote)`), not parameterized calls, because the model
doesn't expose parameterized admin actions — see `NEEDS_MODEL_CHANGE.md`
for why this works reliably here and where it would stop working.

## Captured output of both runs

Full end-to-end demo: `./validate.sh`. Both outcomes below are real
captured output from an actual run (also on disk in `quint-legal.out` /
`quint-stale.out` / `log-legal.json` / `log-stale.json`).

### Outcome 1 — legal workflow, `AUTH_MODE=live`, PASS

Driver log (`log-legal.json`, abridged):

```json
{
  "accepted": [
    {"action": "loginU", "args": {"u": 1}},
    {"action": "submitReviewU", "args": {"u": 1, "a": 1}},
    {"action": "loginU", "args": {"u": 2}},
    {"action": "publishU", "args": {"u": 2, "a": 1}}
  ],
  "rejected": []
}
```

`quint test` output:

```
  generated_trace_legal
    ok traceReplayTest passed 1 test(s)

  1 passing (22ms)
```

alice submits, eve publishes, no admin interference: legal by the model,
confirmed.

### Outcome 2 — stale-session race, `AUTH_MODE=cached`, FAIL (conformance violation)

Scenario: eve logs in (session snapshots her as active editor); alice logs
in and submits article 1; an admin demotes eve; eve's **old** token is
then used to publish. Driver log (`log-stale.json`, abridged):

```json
{
  "accepted": [
    {"action": "loginU", "args": {"u": 2}},
    {"action": "loginU", "args": {"u": 1}},
    {"action": "submitReviewU", "args": {"u": 1, "a": 1}},
    {"action": "adminDemote", "args": {"user": 2}},
    {"action": "publishU", "args": {"u": 2, "a": 1}}
  ],
  "rejected": []
}
```

Note: `publishU` is in `accepted` — the real app, in cached mode, returned
`200` for eve's stale-token publish. That's the bug under test, reproduced
exactly as documented in `../app/README.md`.

`quint test` output:

```
  generated_trace_stale
    1) traceReplayTest failed after 1 test(s)

  1 failed

  1) traceReplayTest:
       Error [QNT508]: Cannot continue to "expect"
        ...
        8:     .then(adminDemote)  // target (from log, informational only): {'user': 2}
        9:     .then(publishU(2, 1))
        10:     .expect(lastActionOk)
    Use --seed=... --match=traceReplayTest to repeat.

error: Tests failed
```

**CONFORMANCE VIOLATION DETECTED**: the app's own accepted-action log,
replayed against the canonical model, cannot be extended through the final
`publishU(2, 1)` step — the model refuses it because eve is no longer an
editor by the time it would commit. The app said `200`; the model says
this trace is impossible. That mismatch *is* the conformance violation,
caught purely from a client-observable log, with no server instrumentation
or special test hooks.

`validate.sh` runs both scenarios back to back and asserts exactly this
pair of outcomes (exit 0 only if legal passes and stale fails); rerunning
it reproduces both deterministically (verified across multiple back-to-back
runs and 10000-sample nondet-action probes — see build notes in
`NEEDS_MODEL_CHANGE.md`).

## Limitations

- **Client-side log != server truth.** The log only records what the HTTP
  client *observed* (status codes, request args it sent). It cannot see
  server-internal state, only ever infers it from admitted requests. If
  the server accepted an action for reasons the model doesn't capture (or
  rejected one it should have accepted), the log alone won't reveal *why*
  — it only tells you *that* the accepted sequence is or isn't legal by
  the model.
- **Single-threaded sessions only.** `driver.py` runs one strictly
  sequential scenario per invocation; the compiled run assumes a single
  total order of actions, matching the model's own interleaving semantics
  for a single trace. Concurrent multi-client logs (several browsers/
  scripts hitting the server at once) would need **ordering metadata** —
  which action's effects were visible to which other action, i.e. a
  partial order or vector-clock-like annotation, not just log-line order —
  to compile into a run at all. That's flagged as a known open problem
  from `research/02` (concurrent/stateful test isolation): without commit-
  order metadata, a merged multi-client log is ambiguous about which
  interleaving actually happened, and the generated-run technique as built
  here has no way to pick among them. Out of scope for this prototype.
- **Admin actions are compiled as bare nondet actions**, not parameterized
  calls, because the model doesn't expose `adminDemoteU(u)`/
  `adminDeactivateU(u)`. This is proven safe *for this driver's fixed
  2-user universe* (the nondet choice is uniquely determined by each
  action's own guard) but would become ambiguous/flaky with more users or
  multiple simultaneously-eligible admin targets. See
  `NEEDS_MODEL_CHANGE.md` for the exact (non-blocking) fix.
- **Fixed, small universe.** Only alice/eve, only 2 articles, only the 5
  action kinds the model exposes. Extending the vocabulary (e.g. archiving,
  editing) needs both a model extension and a driver/log2run extension.

## Verdict for the Track B scoreboard row

**Worked.** The generated-run technique compiles real, HTTP-observed
action logs into concrete Quint runs and gets a real, distinguishing
answer both ways: a legal trace passes, and the actual cached-mode TOCTOU
bug — reproduced by the app, not synthesized — is caught by the model
purely from the client-observable log, with no server instrumentation.
The falsifier in the scoreboard ("the generated-run technique can't
express real logs, or passes traces the model should reject") did not
materialize for the scenarios this prototype covers. The open item is
scoped and non-blocking (parameterized admin actions, `NEEDS_MODEL_CHANGE.md`)
and the acknowledged gap (concurrent/multi-client ordering) is a genuine
open problem shared with `research/02`, not a defect in this approach —
recommend keeping this prototype and, if concurrent traces become a
priority, tackling ordering metadata as its own follow-up rather than
folding it into this one.
