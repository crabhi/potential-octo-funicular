# Bridging requirements ↔ code: parallel tracks

Date started: 2026-07-30. Status: living — this is the phase log for M4.
Mandate: long-horizon; explore several approaches, prototype, and declare
dead ends explicitly. Not limited to Quint.

## Scoreboard

| Track | Approach | Hypothesis | Falsifier | Status |
|---|---|---|---|---|
| A | **Closed repair loop** (`prototypes/p4-agent-loop/`): checker counterexample → headless `claude -p` (Sonnet) repairs → recheck; spec section frozen mechanically | An LLM given a machine-readable counterexample can repair a seeded protocol bug in ≤4 rounds without touching the invariants | Repairs fail, or converge only by weakening the spec (reverted+counted) | in progress |
| B | **Trace validation** (`examples/cms/trace-validation/`): record real app actions, compile the log into a generated Quint run, `quint test` it — "was this a legal behavior of the model?" | Client-side action logs suffice to catch the cached-auth conformance violation from outside the app | The generated-run technique can't express real logs, or passes traces the model should reject | in progress |
| C | **Model-based test generation** (`examples/cms/mbt/`): Quint `--mbt` traces drive the real CMS API; assert acceptance parity model↔app | The generation direction (spec drives app) catches implementation divergence cheaper than trace checking (MongoDB's finding) | Mapping model actions→HTTP is too lossy to give a trustworthy verdict | in progress |
| D | **Dafny: requirements → proven code** (`examples/cms/dafny-authz/`): the 10 CMS rules as Dafny postconditions on an `Authorize` function; prove; compile to Go; embed in a runnable program | A verified decision kernel can be generated from the same requirements and embedded in ordinary code — rung 5 without rewriting the app | Dafny proof or Go compilation is impractical here; or the kernel/app boundary leaks (the caller can still misuse it) | in progress |
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

(appended as results land)
