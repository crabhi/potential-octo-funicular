# Bridging requirements ↔ code: parallel tracks

Date started: 2026-07-30. Status: living — this is the phase log for M4.
Mandate: long-horizon; explore several approaches, prototype, and declare
dead ends explicitly. Not limited to Quint.

## Scoreboard

| Track | Approach | Hypothesis | Falsifier | Status |
|---|---|---|---|---|
| A | **Closed repair loop** (`prototypes/p4-agent-loop/`): checker counterexample → headless `claude -p` (Sonnet) repairs → recheck; spec section frozen mechanically | An LLM given a machine-readable counterexample can repair a seeded protocol bug in ≤4 rounds without touching the invariants | Repairs fail, or converge only by weakening the spec (reverted+counted) | **WORKED** (1 round; exposed a gate gap — see episode log) |
| B | **Trace validation** (`examples/cms/trace-validation/`): record real app actions, compile the log into a generated Quint run, `quint test` it — "was this a legal behavior of the model?" | Client-side action logs suffice to catch the cached-auth conformance violation from outside the app | The generated-run technique can't express real logs, or passes traces the model should reject | **WORKED** |
| C | **Model-based test generation** (`examples/cms/mbt/`): Quint `--mbt` traces drive the real CMS API; assert acceptance parity model↔app | The generation direction (spec drives app) catches implementation divergence cheaper than trace checking (MongoDB's finding) | Mapping model actions→HTTP is too lossy to give a trustworthy verdict | in progress |
| D | **Dafny: requirements → proven code** (`examples/cms/dafny-authz/`): the 10 CMS rules as Dafny postconditions on an `Authorize` function; prove; compile to Go; embed in a runnable program | A verified decision kernel can be generated from the same requirements and embedded in ordinary code — rung 5 without rewriting the app | Dafny proof or Go compilation is impractical here; or the kernel/app boundary leaks (the caller can still misuse it) | **WORKED** (boundary caveat stands) |
| E | **Kani proof spike** (`examples/cms/proof-spike/`): prove the Rust authorization decision satisfies the YAML rules for ALL inputs; compare against plain exhaustive enumeration | Kani is installable/usable here and adds value over exhaustive enumeration for finite domains | Install fails (env), or exhaustive enumeration is strictly simpler at equal assurance for this domain size | in progress |
| — | Alloy 6 for the access rules | (not pursued now) P2/Z3 already covers single-state analysis; Alloy would add instance visualization only | — | parked |
| — | Generate Rust from the Quint spec | No tooling exists (PGo is PlusCal→Go only); would be a research project of its own | — | parked |

## Ground rules (from 07/08)

- The spec is frozen for repair agents; harnesses enforce it mechanically
  (diff the invariant region; revert + count as failed round).
- Counterexample payloads are machine-readable (ITF JSON / pytest output /
  named 403 rules) and cite invariant names.
- A dead end is a result: record what was tried, why it died, and what it
  cost. Parked ≠ dead: parked means consciously not now.

## Episode log

- **Track A result (2026-07-30): WORKED, with a research-grade finding.**
  Sonnet repaired the seeded IS-NULL bug in one round (fixed the switch
  gate to `N == O`), never touched the frozen invariants; 30k traces +
  Apalache green. BUT the fix is sound-yet-partial: backfill still skips
  stale non-NULL rows, so a pre-drain-staled row now blocks the switch
  forever — safety preserved by sacrificing guaranteed completion. The
  safety-only gate accepted a liveness regression, empirically confirming
  the "gates need feature/liveness properties too" thesis (research/08,
  CMS features work). Next iteration: add a temporal completion property
  (under fairness) to the loop's gate.
- **Track D result (2026-07-30): WORKED.** Dafny 4.11 installed via dotnet
  tool; `Authorize` proven against all 10 YAML rules + 3 feature
  guarantees (`1 verified, 0 errors`); compiled to Go and embedded in a
  12-scenario demo (all pass); buggy variant (missing `active` check on
  publish) rejected by the verifier citing the exact violated ensures.
  Standing caveats: YAML→ensures mapping is human-reviewed; the Dafny→Go
  compiler is trusted; nothing forces the app to route through the kernel
  (the boundary problem — candidate fix: generate the app's authorization
  module from this kernel and forbid other role checks by lint).
- **Track B result (2026-07-30): WORKED.** Legal live-mode session replays
  as a passing generated Quint run; the cached-mode stale-token publish is
  accepted by the app (200) but the model refuses the replayed step
  (QNT508 at `.then(publishU(...))`) → conformance violation detected from
  client-side logs only, no app instrumentation. Caveats recorded in the
  track README: client-side logs ≠ server truth; single-threaded sessions
  only; bare nondet admin actions replay deterministically only because
  the 2-user universe makes guards uniquely satisfiable (parameterized
  admin actions now exist in the model for the general case).
