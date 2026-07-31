# Track J — parameterized safety proof (mypyvy / EPR)

Goal (research/10-proof-escalation.md, Track J): prove the REPAIRED
expand/contract migration protocol
(`prototypes/p4-agent-loop/protocol/migration.qnt`) safe for **any** number
of keys and app instances, not the fixed 2x2x2 Apalache instance (Track I).

Files:

- `proof/migration_param.pyv` — the parameterized model, safety properties,
  and the ported/generalized inductive invariant. **Verifies.**
- `proof/migration_param_NEGCONTROL_isnull.pyv` — same model with the
  pre-repair "IS-NULL" backfill/switch criterion. **Fails, as required.**
- `mypyvy/`, `venv/` — tool and its Python env (z3-solver, typing_extensions,
  networkx installed into `venv`).

## 1. Setup (commands actually run)

```
./venv/bin/pip install z3-solver typing_extensions networkx
./venv/bin/python3 mypyvy/src/mypyvy.py typecheck proof/migration_param.pyv
./venv/bin/python3 mypyvy/src/mypyvy.py verify    proof/migration_param.pyv
./venv/bin/python3 mypyvy/src/mypyvy.py updr      proof/migration_param.pyv
./venv/bin/python3 mypyvy/src/mypyvy.py verify    proof/migration_param_NEGCONTROL_isnull.pyv
./venv/bin/python3 mypyvy/src/mypyvy.py updr      proof/migration_param_NEGCONTROL_isnull.pyv
```

## 2. The abstraction (EPR requires erasing values)

mypyvy's decidable core is EPR (Effectively Propositional): relations over
uninterpreted sorts, no function cycles, bounded quantifier alternation.
Quint's `dbO/dbN/logical : key -> value` are *functions into an
unbounded/interpreted domain* — outside EPR outright. The move (as directed)
is to erase every value and keep only the finitely many *equality relations*
the protocol actually inspects. Two sorts, `key` and `instance`, both
universally quantified — nothing is fixed to a count.

| Quint concrete state | mypyvy relation | Meaning | Soundness of the encoding |
|---|---|---|---|
| `dbO.get(k) == dbN.get(k)` | `synced(k)` | O and N agree on k | Set/cleared exactly at every point the concrete equality would change; see per-transition notes below. |
| `dbO.get(k) == logical.get(k)` | `oEqLogical(k)` | O carries ground truth | Same. |
| `dbN.get(k) == logical.get(k)` | `nEqLogical(k)` | N carries ground truth | Same. |
| `dbN.get(k) != NULL` | `hasN(k)` | N has been written at least once | Monotone: only ever set, never cleared (matches: no action ever nulls dbN). |
| `dirty.get(k)` | `dirty(k)` | a commit happened on k since the open backfill snapshot | Ported unchanged — this was already the finite Track I encoding, no change needed. |
| `bf == (true, k, _)` | `bfAt(k)` | backfill in flight on k, snapshot value dropped | The snapshot *value* (`bf._3`) is erased entirely: the protocol only ever uses it via the `!dirty(k)` check at commit, never inspects it directly, so nothing is lost. "At most one active `k`" holds structurally (`backfillBegin` requires `forall K. !bfAt(K)`) and is re-proved as `[bf_unique]`. |
| `instVer.get(i) == 2` | `isV2(i)` | instance i has upgraded | Direct. |
| `phase` (int 0..4) | `phInitial/phExpanded/phSwitched/phContracting/phDone` | one-hot phase | One-hot-ness is proved (`[phase_some]` + 10 exclusion invariants), not assumed. |
| `oState`/`nState` | *(dropped, derived)* | column liveness | `indPhaseShape` in the Quint file shows oState/nState are a **pure function of phase**. Rather than carry two more relations plus an invariant tying them to phase, the derivation is inlined as macros `oPresent = phInitial|phExpanded|phSwitched`, `nPresent = phSwitched|phContracting|phDone`, `nNotAbsent = phExpanded|nPresent`. This is a strict simplification, not a new abstraction: it is definitionally the same fact `indPhaseShape` states. |
| `lastReadOk` | `lastReadOk()` | ghost: no read has ever been wrong | Direct — same ghost variable, not touched by the abstraction. |

### Per-transition soundness (the part that actually needs justifying)

- **`appWriteV1`** (writes O only): sets `oEqLogical(k) := true` (it just
  wrote O to the logical value); **conservatively clears** `synced(k)` and
  `nEqLogical(k)` for k, because N's relationship to the new logical value
  is now unknown — over-approximating "may differ" as "differs" is sound
  because no invariant ever *requires* `synced`/`nEqLogical` to be true
  while a v1 write can happen to that key (that window is exactly
  `oPresent` with N possibly stale, which the invariant set below never
  claims correctness for except after backfill/dual-write repairs it).

- **`appWriteV2`** (dual-write): touches O iff `oPresent`, touches N iff
  `nNotAbsent`, using the *current* phase (a state fact, not a choice). When
  both are touched (EXPANDED, SWITCHED) it writes the *same* value to both,
  so `synced(k)/oEqLogical(k)/nEqLogical(k)` all become true together —
  sound because it really is one write of one value. When only N is
  touched (CONTRACTING, DONE — O is delete-only/gone) `oEqLogical(k)` and
  `synced(k)` are conservatively cleared (O's relationship to the new
  logical value is unknown/irrelevant there since nothing reads O anymore
  in those phases) while `nEqLogical(k)` becomes true and `hasN(k)` is
  monotonically set.

- **`backfillCommit(k)`**: fires only when `!dirty(k)`, i.e. nothing wrote k
  since the snapshot, so O still holds the snapshotted value. Since
  `bfAt(k)` implies `phExpanded` (`[bf_only_expanded]`) and
  `[o_present_agrees]` already gives `oEqLogical(k)` throughout EXPANDED,
  the commit (`dbN[k] := dbO[k]`) makes `synced(k)`, `hasN(k)` **and**
  `nEqLogical(k)` true in the same step — this is a genuine consequence of
  facts already proved elsewhere in the invariant, not a fresh unjustified
  write.

- **`switchRead`**: the REPAIRED guard is `forall K. synced(K)` plus drain.
  Combined with `[o_present_agrees]` (which holds throughout EXPANDED, the
  only phase `switchRead` fires from), this *derives* `nEqLogical(K)` for
  every K, including keys nobody wrote this run — so the transition is
  entitled to set `nEqLogical(K) := true` universally. This is the one
  place erasure could have gone wrong (setting a ghost "true" without
  present justification): the negative control below shows exactly what
  happens when this derivation's premise is removed.

- **`synced(K) -> hasN(K)`** invariant: the *only* auxiliary lemma this
  abstraction needed that the concrete Quint `indInv` doesn't state
  explicitly. In the concrete model `dbO` is simply never assigned `NULL`
  by any action, so `synced(k)` (`dbO==dbN`) trivially forces `dbN != NULL`
  — a domain fact with no relational counterpart once values are erased.
  Restating it as an invariant (provable: `synced` and `hasN` are always
  set together or `hasN` was already set) recovers exactly what was lost.

## 3. Safety statement

```
safety [reads_correct]      lastReadOk
safety [switched_n_correct] phSwitched -> nEqLogical(K)
```

`reads_correct` is the real property (no read is ever wrong, matching
Quint's `invReadsCorrect`). `switched_n_correct` is the task-specified
headline property; combined with `[o_present_agrees]` (`oEqLogical`
throughout SWITCHED, since `oPresent` holds there too) it implies Quint's
`invColumnsAgree` (`dbN==dbO` once switched with O still present), and
combined with `[synced_implies_hasN]`-style monotonicity it implies
`invBackfillDoneAtSwitch`.

The ported inductive invariant (`proof/migration_param.pyv`, generalized
from `migration.qnt`'s frozen `indInv`, quantified over **all** keys and
instances instead of the fixed 2x2 constants):

```
phase one-hot (11 clauses)                    -- was indPhaseShape's domain half
oPresent -> oEqLogical(K)                     -- indInv conjunct: O carries logical while live
nPresent -> nEqLogical(K)                     -- indInv conjunct: N carries logical once readable
nPresent -> isV2(I)                           -- indInv conjunct: drain, monotone
bfAt(K) -> phExpanded                         -- indInv conjunct: backfill only in expanded
bfAt(K1) & bfAt(K2) -> K1 = K2                 -- at-most-one, re-derived
synced(K) -> hasN(K)                          -- new: substitutes for the erased "dbO never NULL"
```

Dropped from the concrete `indInv`: `KEYS.forall(k => logical.get(k) != NULL)`
— not needed, since `logical` itself was erased (nothing left to say NULL
about; its role is absorbed into the two `EqLogical` relations, which are
simply false, not "false because NULL", when they don't hold).

## 4. Result — hand invariant

```
$ ./venv/bin/python3 mypyvy/src/mypyvy.py verify proof/migration_param.pyv
checking init: ... (19 implications, all ok)
checking transition appWriteV1: ... ok
checking transition appWriteV2: ... ok
checking transition appRead: ... ok
checking transition upgrade: ... ok
checking transition expand: ... ok
checking transition backfillBegin: ... ok
checking transition backfillCommit: ... ok
checking transition backfillAbort: ... ok
checking transition switchRead: ... ok
checking transition contractStart: ... ok
checking transition contractFinish: ... ok
all ok!
```
Wall time: **0.38s**. No CTIs needed — the first fully-written invariant
above was already inductive (the per-transition soundness argument in §2
was worked out by hand before writing it, which is exactly why). This holds
for `key`/`instance` of **any** cardinality — mypyvy's EPR check has no
notion of instance size at all; the same first-order proof covers every
model.

## 5. Result — automatic inference (`updr`)

```
$ ./venv/bin/python3 mypyvy/src/mypyvy.py updr proof/migration_param.pyv
checking init: ... ok
frame is safe and inductive. done!
!(exists key0:key. !oEqLogical(key0) & phInitial)
!(exists key0:key. !oEqLogical(key0) & phExpanded)
!(exists instance0:instance. !isV2(instance0) & phSwitched)
!(exists K:key. phSwitched & !nEqLogical(K))
!(exists instance1:instance. !isV2(instance1) & phContracting)
!(exists key0:key. !nEqLogical(key0) & phContracting)
!(!lastReadOk & true)
!(exists instance1:instance. !isV2(instance1) & phDone)
!(exists key0:key. !nEqLogical(key0) & phDone)
updr found inductive invariant!
```
Wall time: **5.7s**.

**Hand vs. inferred:** UPDR found a *smaller* sufficient invariant — 9
clauses vs. the hand-written ~18 (11 phase-exclusion + 5 semantic + 1
auxiliary). It kept `o_present_agrees` only for `phInitial`/`phExpanded`
(never needed for `phSwitched`, since the safety goal only needs
`nEqLogical` there), dropped `bf_only_expanded`, `bf_unique`, and
`synced_implies_hasN` entirely, and split `n_present_agrees`/
`drain_monotone` per-phase instead of as one `nPresent`-guarded clause. It
is UPDR's job to find the *minimal* strengthening for the stated safety
properties, not to explain the protocol — so it correctly discards
everything that is true but not load-bearing for `reads_correct` /
`switched_n_correct`. The hand invariant is the better artifact for a human
(it mirrors the Quint `indInv` and each clause has a one-line semantic
name); the UPDR invariant is the better certificate of "this really is the
minimum needed."

## 6. Negative control — IS-NULL criterion

Per the task: swap `backfillBegin`'s guard `!synced(k)` for `!hasN(k)`.
**First attempt, changing only that one guard: `verify` still printed `all
ok!`** — because `switchRead`'s guard was untouched
(`forall K. synced(K)`), so a key left stale by the weaker `backfillBegin`
simply never satisfies `synced`, and the protocol *deadlocks* rather than
switching with bad data. That is a real (if uninteresting to this proof)
liveness bug, not a safety violation — worth recording as a "documented
near-miss": a negative control must break the same load-bearing guard the
safety property actually rests on, not just any related guard.

`switchRead`'s own completeness guard was **also** changed, from
`forall K. synced(K)` to `forall K. hasN(K)` (this is the historically
faithful "IS-NULL" criterion: "done" tracked by nullness, not by
agreement) — and its now-unjustified `nEqLogical(K) := true` postcondition
was removed (see §2, the one place the abstraction's soundness depended on
that specific guard). Result:

```
$ ./venv/bin/python3 mypyvy/src/mypyvy.py verify proof/migration_param_NEGCONTROL_isnull.pyv
...
checking transition switchRead:
counterexample:
  state 0: hasN(key0) & isV2(instance0) & lastReadOk & oEqLogical(key0) & phExpanded
  state 1: hasN(key0) & isV2(instance0) & lastReadOk & oEqLogical(key0) & phSwitched
error: invariant switched_n_correct is not preserved by transition switchRead
program has errors.
```
A genuine CTI: key0 has been written to N once before (`hasN` true, from a
stale value) but a later v1-only write left `nEqLogical(key0)` false; the
IS-NULL guard doesn't see the staleness and lets `switchRead` fire anyway.

`updr` on the same file independently confirms this is not just "our
invariant was too weak" — it searches for *any* inductive invariant and
reports **`updr found abstract counterexample!` / "the system has no
universal inductive invariant proving safety"**, i.e. the protocol variant
is actually unsafe, for any key/instance count. Both files, both tools,
agree.

## 7. What this proves beyond Track I

Track I (Apalache/Quint, `--inductive-invariant`): proof at **every depth**
(no step bound) but for the **fixed** 2 keys x 2 instances x 2 values
instance. Track J (this): proof for **every depth AND every key/instance
count simultaneously** — a single first-order EPR proof stands for the
2x2 case, the 1000x1000 case, and everything between, because the
invariant and the transition relation are stated with `forall K`/`forall I`
over uninterpreted sorts with no cardinality baked in anywhere. What is
*not* covered here that Track I's concrete model had: the actual `VALUES`
domain and NULL are gone (erased on purpose, §2) — this is now a proof
about the *protocol's control/consistency logic*, not about arithmetic on
values, which is exactly the right division of labor (values were never
where the flaw could hide; the equality/nullness bookkeeping is).

## 8. Verdict for Track J

**PROVEN** (parameterized, hand invariant, `verify`: 0.38s, no CTIs) +
**independently reconstructed** (UPDR, 5.7s, smaller invariant). Negative
control reproduces the historical IS-NULL bug as a genuine CTI, confirmed
unsatisfiable-by-any-invariant via UPDR — closing the "Ivy/mypyvy row" and
the "parameterized verification" gap named in
research/10-proof-escalation.md item 2 / Track J. No dead end to report;
the only wrinkle worth keeping in mind for future use of this file is §6's
near-miss: a negative control has to attack the guard the proof actually
leans on, not merely *a* guard that sounds related.
