# Proof escalation: the novel concepts we are missing

Date: 2026-07-31. Status: living — phase 3 charter.
Trigger: developer directive — "prove something never/always happens;
tests are only an approximation."

## Self-audit: where we currently approximate

| Artifact | Current evidence | Class |
|---|---|---|
| Migration/CMS models | `quint run` 10-30k random traces | sampling (approximation) |
| Same, `quint verify` | Apalache, bounded to k steps, fixed tiny constants | proof, but **depth- and size-bounded** |
| Completion (`featDone`) | witness counts over random traces | sampling |
| Feature runs | single scripted executions | example, not proof |
| App conformance (P3, MBT, trace validation) | finite test suites | sampling |
| Authorization kernel | Dafny proof / Kani / exhaustive 64-pt | **proof** (finite domain) |
| Kernel boundary | compile error (type system) | **proof** (by construction) |
| Optimization gate (P5) | test suites + benchmark | sampling |

## The missing concepts (each is a genuinely different idea, not more tests)

1. **Inductive invariants** — an invariant `Ind` with `Init ⇒ Ind` and
   `Ind ∧ Next ⇒ Ind'` holds at EVERY depth, forever — no step bound.
   Quint/Apalache support this today (`--inductive-invariant`), we never
   used it. The craft is *strengthening*: the property you care about is
   rarely inductive by itself. Related: IC3/PDR can infer the
   strengthening automatically. → Track I (migration protocol), Track J
   (inference).
2. **Parameterized verification** — our proofs fix 2 keys/2 instances/2
   users. "Never happens" should mean for ANY system size. Tools: EPR
   fragment (Ivy/mypyvy, PDR∀ invariant inference), or cutoff theorems
   ("if safe for N≤3, safe for all N"). This un-parks the Ivy/mypyvy row
   from note 09. → Track J.
3. **Refinement mappings** — prove one spec implements another
   (simulation relation), instead of testing agreement. Two uses here:
   (a) serializable model ⊑ snapshot-isolation model (the brief's
   "start simple, extend" made rigorous); (b) an app-shaped low-level
   model ⊑ the abstract model — turning the model↔code link from tests
   (tracks B/C) into a proof about the code's *design*, shrinking the
   tested residue to "code matches low-level model". → Track N (later).
4. **Liveness under fairness, as proof** — "always eventually" checked as
   a temporal proof obligation (`quint verify --temporal`, or TLC with
   weak-fairness on compiled TLA+), replacing witness sampling. The P4
   episode-1 gap (accepted liveness regression) gets a *proof-shaped*
   gate instead of scripted-run patches. → Track M.
5. **Hyperproperties** — the sharpest conceptual gap. "Anonymous users
   never learn draft content" is NOT a property of one trace; it relates
   PAIRS of traces (noninterference, a 2-safety property). Our entire
   invariant language so far cannot even state it: a per-request
   authorization check does not rule out leaks via error messages,
   timing-shaped response differences, or id enumeration. Technique:
   **self-composition** — run two copies of the system that agree on
   everything except secret (draft) data; prove anonymous-observable
   outputs identical. → Track K.
6. **Proof-carrying repair gates** — P4/P5 gates return green/red from
   checks; the stronger form makes the agent maintain a PROOF ARTIFACT
   (the inductive invariant, the refinement mapping) that the gate merely
   re-checks. Repairs that can't re-establish the proof are rejected by
   construction; gate strength stops depending on which tests we thought
   to write. → fold into P4 once Track I lands.
7. **Verified runtime enforcement (shielding)** — when code can't be
   proven, a monitor synthesized FROM the spec sits in front of effects
   and blocks any action that would violate the invariant — "never
   happens" guaranteed at runtime by construction, even over unverified
   code. (The Grant token is the static cousin; this is the dynamic one.)
   → Track O (later; candidate: migration-state transitions).
8. **Compositional assume-guarantee** — scale proofs beyond monoliths:
   kernel proven under assumptions A; app proven to establish A; composed
   theorem about the whole. Today our composition argument is prose.
9. **TCB accounting as a first-class artifact** — every proof trusts
   something (Dafny→Go compiler, Apalache, the YAML→ensures mapping, the
   HTTP layer). A machine-readable trusted-computing-base inventory per
   guarantee keeps "proven" honest and directs the next escalation.
10. **Deductive theorem proving (TLAPS/Lean)** — beyond model checking
    entirely: unbounded depth AND unbounded domains AND no SMT-fragment
    limits, at high human cost. The escalation endpoint, used sparingly.

## Phase 3 tracks

| Track | What gets PROVEN | Tool | Status |
|---|---|---|---|
| I | Migration safety at every depth (inductive invariant, fixed constants) | Quint/Apalache `--inductive-invariant` | **PROVEN** (both models; see episode log) |
| J | Same protocol, ANY number of keys/instances (parameterized) + invariant inference | mypyvy (PDR∀) / Ivy | in progress |
| K | CMS noninterference: draft contents never influence anonymous observations (hyperproperty via self-composition) | Quint/Apalache on self-composed model | **PROVEN** (inductive, safe config) + machine-found leak distinguisher (leaky config) |
| L | Real Rust code proof beyond the pure kernel: session/identity state machine in the app | Dafny (Verus proxy-blocked) | **PROVEN** — freshness, revocation/demotion immediacy, cached-stale witness; buggy variant rejected |
| M | Migration completion: liveness under fairness as a temporal proof | TLC + WF (hand-ported TLA+) | **PROVEN, stronger than designed** — no interference assumption needed; rollout fairness shown necessary |
| N | Refinement: serializable ⊑ SI; app-level model ⊑ abstract model | TLA+ refinement mapping | planned |
| O | Verified enforcement monitor for migration-state transitions | synthesized from spec | planned |

## Episode log

- **Track M (2026-07-31): PROVEN, and it falsified the author's
  prediction favorably.** TLC (complete state graph, 623 states):
  `<>(phase=DONE)` HOLDS under weak fairness of migration+rollout actions
  even with UNBOUNDED app-write interference — the anticipated
  backfill-starvation lasso is structurally impossible because post-drain
  writes are dual-writes: aborting a backfill syncs the row being copied.
  Negative control: dropping rollout fairness alone yields the
  stalled-deploy lasso, so that assumption is necessary. The theorem:
  this migration fails to complete only if the deploy itself stalls.
  (Track K, same day: noninterference proven inductively via
  self-composition; leaky-search variant yields a machine-found two-world
  distinguisher — see examples/cms/noninterference/.)
- **Track L (2026-07-31): PROVEN (Dafny; Verus release downloads
  proxy-blocked).** Session/identity state machine extracted from main.rs
  (cited lines): FreshnessLive, RevocationImmediate, DemotionImmediate
  proven (14/14 VCs); CachedStaleAfterDeactivation as a machine-checked
  existence witness — the code-level twin of the model's CHECK_AT_ACTION
  CTI. Buggy resolver correctly rejected (2 errors — it breaks freshness
  too, a bonus finding). Open gap: extraction fidelity (reviewed-by-eye vs
  main.rs); closing paths documented (codegen like dafny-authz,
  differential proptest, Verus retry with network).
- **Track I (2026-07-31): PROVEN.** (a) Migration protocol: replaced the
  unbounded SI version counter with an equivalent finite dirty-flag
  encoding, wrote the 7-conjunct strengthening (phase-shape coupling,
  O==logical while O live, N==logical once N readable, drain monotone,
  backfill-only-in-expanded, logical≠NULL) + Apalache shape constraints;
  all three obligations verified in ~10s. Safety now holds at EVERY depth
  (fixed 2x2x2 constants — Track J owns the size generalization).
  (b) CMS model: for cms_live the invariant is inductive with essentially
  NO strengthening beyond the ghost itself — live guards re-establish the
  policy at every step (proof-shaped evidence that check-at-use is the
  structurally right design). The SAME invariant fails consecution on
  cms_cached with a concrete CTI (cached EDITOR, demoted live role): the
  live/cached asymmetry is now a machine-checked theorem pair, not a
  simulation finding. Lesson worth keeping: "how much strengthening does
  the proof need" is itself a design-quality signal.
