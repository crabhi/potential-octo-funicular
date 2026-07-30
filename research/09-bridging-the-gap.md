# Bridging requirements ↔ code: parallel tracks

Date started: 2026-07-30. Status: living — this is the phase log for M4.
Mandate: long-horizon; explore several approaches, prototype, and declare
dead ends explicitly. Not limited to Quint.

## Scoreboard

| Track | Approach | Hypothesis | Falsifier | Status |
|---|---|---|---|---|
| A | **Closed repair loop** (`prototypes/p4-agent-loop/`): checker counterexample → headless `claude -p` (Sonnet) repairs → recheck; spec section frozen mechanically | An LLM given a machine-readable counterexample can repair a seeded protocol bug in ≤4 rounds without touching the invariants | Repairs fail, or converge only by weakening the spec (reverted+counted) | **WORKED** (1 round; exposed a gate gap — see episode log) |
| B | **Trace validation** (`examples/cms/trace-validation/`): record real app actions, compile the log into a generated Quint run, `quint test` it — "was this a legal behavior of the model?" | Client-side action logs suffice to catch the cached-auth conformance violation from outside the app | The generated-run technique can't express real logs, or passes traces the model should reject | **WORKED** |
| C | **Model-based test generation** (`examples/cms/mbt/`): Quint `--mbt` traces drive the real CMS API; assert acceptance parity model↔app | The generation direction (spec drives app) catches implementation divergence cheaper than trace checking (MongoDB's finding) | Mapping model actions→HTTP is too lossy to give a trustworthy verdict | **WORKED** (240/240 parity, 6/6 divergences caught) |
| D | **Dafny: requirements → proven code** (`examples/cms/dafny-authz/`): the 10 CMS rules as Dafny postconditions on an `Authorize` function; prove; compile to Go; embed in a runnable program | A verified decision kernel can be generated from the same requirements and embedded in ordinary code — rung 5 without rewriting the app | Dafny proof or Go compilation is impractical here; or the kernel/app boundary leaks (the caller can still misuse it) | **WORKED** (boundary caveat stands) |
| E | **Kani proof spike** (`examples/cms/proof-spike/`): prove the Rust authorization decision satisfies the YAML rules for ALL inputs; compare against plain exhaustive enumeration | Kani is installable/usable here and adds value over exhaustive enumeration for finite domains | Install fails (env), or exhaustive enumeration is strictly simpler at equal assurance for this domain size | **HYPOTHESIS FALSIFIED for finite domains, Kani wins at scale** — "later, not now, not never" |
| — | Alloy 6 for the access rules | (not pursued now) P2/Z3 already covers single-state analysis; Alloy would add instance visualization only | — | parked |
| — | Generate Rust from the Quint spec | No tooling exists (PGo is PlusCal→Go only); would be a research project of its own | — | parked |

## Phase 2 (started 2026-07-30): strong guarantees over NL guidance

Directive from the developer: prefer mechanical guarantees to steering the
LLM with natural language. Consequences: repair prompts stay generic; all
correctness pressure moves into frozen, machine-checked gates; boundaries
become type errors instead of conventions.

| Track | Approach | Hypothesis | Falsifier | Status |
|---|---|---|---|---|
| F | **Gate-strengthened repair loop**: add frozen feature runs (adversarial stale-row recovery, happy path) + completion-reachability witness to P4's gate; re-run the episode from the original double-bug protocol with the SAME generic prompt | The strengthened gate alone forces the full fix (episode 1's partial fix gets rejected mechanically) | The repairer stalls, or games the gate some third way the runs don't cover | **WORKED** — full fix in 1 round; controlled comparison in P4 README |
| G | **Type-enforced kernel boundary** (`examples/cms/`): protected app operations require a `Grant<Op>` token only the verified kernel can mint | Bypassing the kernel becomes a compile error, with the app harness and kernel proofs staying green | The typestate refactor breaks the app/race semantics, or meaningful checks can't be tokenized | **WORKED** (compile-fail pinned; harness identical; proofs green) |
| H | **Gated performance optimization of real code** (`prototypes/p5-optimization-loop/`): agent maximizes benchmark rps on the CMS app (seeded Mutex + fingerprint-under-lock defects); frozen gate = boundary lint + policy + race suites; frozen paths enforced by git | The agent finds real, safe speedups; correctness-violating "optimizations" (e.g. identity caching) get mechanically rejected | No accepted improvement, or the gate misses a behavior change | in progress |

## Ground rules (from 07/08)

- The spec is frozen for repair agents; harnesses enforce it mechanically
  (diff the invariant region; revert + count as failed round).
- Counterexample payloads are machine-readable (ITF JSON / pytest output /
  named 403 rules) and cite invariant names.
- A dead end is a result: record what was tried, why it died, and what it
  cost. Parked ≠ dead: parked means consciously not now.

## Episode log

- **Track F result (2026-07-30): WORKED — the phase-2 flagship.** Same
  double-bug protocol, same Sonnet repairer, same generic prompt as
  episode 1; only the gate changed (added frozen feature runs + completion
  witness). Episode 1 (safety-only gate): sound-but-partial fix, latent
  liveness regression accepted. Episode 2 (strengthened gate): FULL fix in
  one round (IS-DISTINCT backfill + N==O switch), 30k traces + Apalache
  clean, completion witnessed in 84% of traces. Controlled comparison
  table in prototypes/p4-agent-loop/README.md. Conclusion: with LLM
  repairers, invest in gate strength, not NL steering.
- **Track G result (2026-07-30): WORKED.** `Grant<Op>` capability tokens
  (sealed, non-forgeable) minted only by `authz::require`; all four
  protected handlers hold zero raw role checks; forging a Grant (E0639)
  and using the wrong op token (E0308) are pinned compile-fail tests;
  boundary lint as belt-and-suspenders; app harness identical
  (5/5, 2/2, 2/2); kernel tests 11/11 and Kani unchanged. Remaining
  conventions documented: admin endpoints out of scope; identity
  freshness is AUTH_MODE's guarantee, not the kernel's.

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
- **Track C result (2026-07-30): WORKED.** 20 model-generated traces
  (`--mbt` metadata) replayed against the real live-mode app: 240/240
  steps accepted, 0 state mismatches (3 identical consecutive runs). The
  divergence leg replayed 6 cms_cached race counterexamples onto the live
  app: 6/6 rejected at exactly the step the cached-semantics model wrongly
  allowed (named 403s), 0 silent vulnerabilities. `mbt::nondetPicks` made
  argument recovery trivial; real friction = app seed state vs model init
  (needed an explicit setup phase) and recursive ITF record decoding.
- **Track E result (2026-07-30): the falsifier fired, informatively.** At
  the 64-point domain, exhaustive enumeration matches Kani's assurance at
  zero setup cost (5 tests, ~0.4s; buggy variant caught with 18 concrete
  violations). But Kani installed cleanly (36s total) and proved the same
  rules over a ~2^131-point id-domain variant in ~0.1s per harness, where
  exhaustive extrapolates to ~10^21 years. Verdict: exhaustive for finite
  decision kernels today; Kani the moment unbounded types (ids, strings)
  enter the kernel's signature. A real methodological catch: unreachable
  input combinations (anonymous ∧ is_author) must be excluded by
  precondition on BOTH sides (filter / kani::assume) or rules get judged
  on impossible states.
- **Track B result (2026-07-30): WORKED.** Legal live-mode session replays
  as a passing generated Quint run; the cached-mode stale-token publish is
  accepted by the app (200) but the model refuses the replayed step
  (QNT508 at `.then(publishU(...))`) → conformance violation detected from
  client-side logs only, no app instrumentation. Caveats recorded in the
  track README: client-side logs ≠ server truth; single-threaded sessions
  only; bare nondet admin actions replay deterministically only because
  the 2-user universe makes guards uniquely satisfiable (parameterized
  admin actions now exist in the model for the general case).
