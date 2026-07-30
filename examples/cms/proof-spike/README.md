# Track E: Kani proof spike vs. plain exhaustive enumeration

Hypothesis (from `research/09-bridging-the-gap.md`): Kani is
installable/usable here and adds value over exhaustive enumeration for
finite domains. Falsifier: install fails, or exhaustive enumeration is
strictly simpler at equal assurance for this domain size.

**Result: the falsifier held.** Install succeeded (see below) but bought
nothing at this domain size. Exhaustive enumeration is already proof-grade
and free. Kani's value shows up only once you leave the finite domain — see
"the crossover" below, which is empirical, not hand-waved.

## What was built

`src/lib.rs` extracts the CMS authorization decision into one pure function:

```rust
pub fn authorize(role: Role, is_author: bool, active: bool, state: ArticleState) -> Perms
```

Faithfully ported from `examples/cms/app/server/src/main.rs`, `AUTH_MODE=live`
semantics (every request re-reads current role/active — the pure-function
case; `cached` mode's stale-session bug is Track B/C's territory, not this
one). Cited source lines are in the doc comment on `authorize`:

- view: main.rs:282-301 (deactivated viewer folds to Anonymous, then the
  per-state `can_view` match)
- edit: main.rs:349-366 (active gate, is_author/editor/admin gate, the
  author-only "unpublished" restriction)
- publish: main.rs:410-419 (active gate, editor/admin gate, in-review gate)

All 10 YAML rules from `examples/cms/invariants/cms-security.yaml` are
Rust predicates named after the rule (`inv_published_is_public`, etc.),
plus 3 feature predicates (`feature_active_editor_views_drafts`, ...) that
require some access to actually be granted — insurance against an all-deny
stub vacuously satisfying every rule.

A second function, `authorize_buggy_missing_active_check`, is `authorize`
with the `active &&` guard dropped from `can_edit` — a realistic
"someone simplified this during a refactor" regression.

A third function, `authorize_by_id`, replaces the `is_author: bool` input
with two `u64` ids and an equality check — the crossover experiment (below).

## The 11th rule: a finding, not a footnote

`inv_anonymous_never_author` ("an anonymous visitor is by definition not the
author of anything") doesn't mention `can_view`/`can_edit`/`can_publish` at
all — it's a constraint on the *shape of the input*, not a property of
`authorize()`'s output. The first version of the exhaustive test iterated
the raw, unfiltered 64-point grid and immediately failed:

```
rule inv_anonymous_published_only violated by input
  (Anonymous, is_author=true, active=true, Draft) -> Perms { view: true, edit: true, publish: false }
```

That's real: `authorize()` has no defense against a caller claiming
`is_author=true` while `role=Anonymous`. The real app never constructs that
input (`resolve_identity`/`get_article`, main.rs:277-294, always pairs
`Anonymous` with `is_author=false`), but the pure function doesn't enforce
its own precondition. The fix — filtering the 8 impossible tuples out of the
64 before checking the other 9 rules, exactly mirroring `inv_anonymous_never_author`
itself — reduces the *reachable* domain to 56 and is applied identically on
both sides: `.filter()` in the Rust loop, `kani::assume(...)` in every Kani
harness. Skipping either would (correctly) manufacture a spurious
counterexample. This is a genuine parity point between the two techniques,
not a Kani-specific wrinkle.

## Results — run and captured on 2026-07-30

### 1. Exhaustive enumeration (`cargo test`)

```
running 5 tests
test tests::exhaustive_all_reachable_inputs_satisfy_all_9_output_rules ... ok
test tests::feature_predicates_are_satisfiable ... ok
test tests::exhaustive_sweep_catches_missing_active_check ... ok
test tests::inv_anonymous_never_author_describes_reachable_inputs ... ok
test tests::bounded_id_domain_exhaustive_timing ... ok

test result: ok. 5 passed; 0 failed
```

- `exhaustive_all_reachable_inputs_satisfy_all_9_output_rules`: all 56
  reachable points of the 4x2x2x4 grid, all 9 output rules. **This is the
  proof.** Total wall-clock including compile: well under a second
  (`cargo test` real time: ~0.4s; the loop body itself is microseconds).
- `exhaustive_sweep_catches_missing_active_check`: runs the same 9 rules
  against `authorize_buggy_missing_active_check` and asserts the deliberate
  bug is caught — 18 violations found (Editor/Admin can now edit while
  deactivated in all 4 states each = 16, plus deactivated authors editing
  their own draft/in-review work = 2). Confirms the technique isn't
  vacuous.
- `bounded_id_domain_exhaustive_timing`: see "the crossover" below.

### 2. Kani install + setup

```
$ cargo install kani-verifier      # 12.1s wall clock
$ cargo kani setup                 # 23.7s wall clock (downloads CBMC + a
                                    #   pinned nightly toolchain)
```

Total install overhead: **~36 seconds**, no manual intervention, no proxy
issues (crate downloads went through `static.crates.io` via the environment's
HTTPS proxy without incident). This environment made the install cheap; the
hypothesis's install-risk falsifier did not trigger here. That won't be true
in every environment (offline CI runners, restricted egress, ARM hosts
without prebuilt CBMC — Kani's setup step downloads a release bundle per
platform), so "cheap to install" is a property of *this* sandbox, not a
guarantee.

### 3. Kani proof harnesses (`cargo kani`)

One `#[kani::proof]` harness per rule (9), one for the deliberate bug
(expected to fail), three for the id-keyed crossover variant (see below):

```
Manual Harness Summary:
Verification failed for - kani_harness::kani_buggy_variant_violates_deactivated_does_nothing
Complete - 12 successfully verified harnesses, 1 failures, 13 total.
```

- All 9 finite-domain rule harnesses: **SUCCESSFUL**.
- The buggy-variant harness: **FAILED**, exactly as designed — Kani finds
  the same `inv_deactivated_does_nothing` violation the exhaustive test
  finds. (Filtering that one harness out, `cargo kani` exits 0 — confirmed
  separately by running the 12 "should-pass" harnesses alone.)
- Wall-clock for the full 13-harness run: **~5 seconds** (`cargo kani`,
  including CBMC/SAT-solving for every harness). Per-harness verification
  time reported by CBMC: 0.07-0.15s each, regardless of whether the harness
  covers the 64-point finite domain or the ~2^131-point id domain (next
  section) — that's the whole story of *why* Kani doesn't care about domain
  size once it's past install.

## The crossover: when does the domain stop being finite?

`authorize`'s `is_author: bool` is a stand-in for what the real app
actually does: compare two identities
(`user == article.author`, main.rs:289 — `String`s in this demo, `u64`
primary keys in most production schemas). `authorize_by_id` makes that
explicit:

```rust
pub fn authorize_by_id(role: Role, active: bool, state: ArticleState, viewer_id: u64, author_id: u64) -> Perms {
    authorize(role, viewer_id == author_id, active, state)
}
```

Nominal domain size: 4 (role) x 2 (active) x 4 (state) x 2^64 (viewer_id) x
2^64 (author_id) ~= **2^131 points**. Two things happen to the two
techniques:

**Exhaustive enumeration dies immediately, and it's not close.**
`bounded_id_domain_exhaustive_timing` ran a *deliberately tiny* slice — ids
0..1000 on each side, 32,000,000 concrete tuples after filtering — through
the exact same "loop and assert 9 rules" style as the 56-point test, in
release mode:

```
bounded_id_domain_exhaustive_timing: checked 31992000 tuples (N=1000) in 3.984096ms
(≈ 8.0 x 10^9 tuples/sec on this machine)
```

Extrapolating that measured throughput to the real `u64 x u64` space
(ignoring the small x32 multiplier from role/active/state, which doesn't
change the order of magnitude): 2^128 ≈ 3.40 x 10^38 tuples, at
~8 x 10^9 tuples/sec, is **≈ 4.3 x 10^28 seconds ≈ 1.4 x 10^21 years** — about
10^11 times the current age of the universe (~1.4 x 10^10 years). This is
not "leave it running overnight"; it's "not a technique" at this domain
size. No amount of engineering effort (parallelism, faster hardware, GPU)
closes 21 orders of magnitude.

**Kani doesn't notice.** The three id-variant harnesses
(`kani_id_inv_edit_rights`, `kani_id_inv_authors_edit_unpublished_only`,
`kani_id_inv_draft_visibility`) each declare `viewer_id`/`author_id` as
fully unconstrained `kani::any::<u64>()` and prove the rule for *all* of
2^131 — not a sample, the actual full space, because CBMC reasons about
`viewer_id == author_id` as a symbolic bitvector equality rather than
concretely trying values. Verification time per harness: 0.07-0.15s,
indistinguishable from the finite-domain harnesses. This is the actual
payoff of bounded model checking over brute force: it substitutes symbolic
reasoning about *relations between* unbounded values for enumeration
*over* them.

**The concrete crossover for this codebase:** the moment `is_author` (or
any other rule input) stops being a bool/small-enum and becomes a string,
a u64 id, a timestamp, or anything else with a domain too large to loop
over concretely, exhaustive enumeration stops being a viable proof
technique — not "slower," but off the table — while Kani's cost is
unchanged. In this app specifically, the real `is_author` computation
(`user == article.author`, both `String`) is *already* on the far side of
that crossover; the `bool` flag in `authorize()`'s signature is a
faithful-but-idealized abstraction of a String comparison that the
64-point exhaustive test can only certify indirectly (by assuming that
comparison behaves like an opaque bool, which it does — `==` on two
Strings is decidable and total — but the exhaustive test never actually
exercises string identity, whereas the Kani id-harness exercises the
literal `u64`-keyed version of it end to end).

## Comparison table

| Dimension | Exhaustive enumeration (`cargo test`) | Kani (`cargo kani`) |
|---|---|---|
| Assurance at 64/56-point domain | Proof-grade — every point checked, not sampled | Proof-grade — same claim, same result |
| Setup cost | Zero (stdlib `#[test]`, already in every Rust project) | ~36s one-time install (`cargo install` + `cargo kani setup`); a pinned nightly toolchain + CBMC bundle land in `~/.kani` |
| Runtime at 64/56-point domain | <1ms loop body; ~0.4s total incl. compile | ~5s for 13 harnesses (~0.1s CBMC/SAT time each, plus process/compile overhead) |
| Failure reporting | Plain Rust panic message with the offending tuple + rule name — reads like the app's own named-403 convention | CBMC counterexample trace with concrete witness values; more verbose, needs translation back to domain vocabulary |
| Expressiveness at this domain size | Full — can express every rule Rust can express as a bool predicate | Full, plus symbolic reasoning that generalizes free of charge to non-enumerable inputs |
| Scales to u64/String-keyed inputs | No — exhaustive becomes physically impossible past ~10^10-10^12 concrete points; measured throughput here is ~8x10^9/sec, so u64x u64 is ~10^21 years, off the table entirely | Yes — proved 2^131 points in the same ~0.1s per harness as the 64-point case; cost is a function of predicate/solver complexity, not domain cardinality |
| Team/tooling burden | None — it's a `#[test]`, runs in every CI already configured for `cargo test` | New toolchain in CI, nightly Rust pin, longer (though still fast) `cargo kani` step, unfamiliar output format for anyone not already doing bounded model checking |

## Verdict for the Track E scoreboard row

**Kani is: later — not now, not never.**

- **Now**: for the actual 4-role x 2-author x 2-active x 4-state CMS
  decision kernel as it exists today, exhaustive enumeration is strictly
  better — same assurance, zero install cost, faster, and its failure
  output already speaks the app's own "named invariant" vocabulary. Adding
  Kani today would be paying a toolchain tax for no additional assurance.
  Confirmed: **for finite decision kernels, exhaustive enumeration is
  already proof-grade and free.**
- **Later**: the instant `is_author`/role/state stop being small enums —
  the moment the real `String`-keyed or `u64`-keyed identity comparison
  (main.rs:289's `user == article.author`) is what's being verified,
  rather than a `bool` abstraction of it, or the moment `session_ttl_minutes`
  (already in the YAML schema, `min:0 max:1440` — 1441 values, still
  technically finite but 22x bigger than the current domain and only
  getting worse if that range ever widens) enters an invariant, exhaustive
  enumeration's days are numbered and Kani is already proven (this spike)
  to absorb that growth for free.
- **Never** applies to nothing observed here — there's no evidence Kani
  is unusable or not worth its cost *in general* for this codebase; the
  "never" branch of the hypothesis (install fails / impractical) simply
  didn't happen.

Recommendation: don't adopt Kani for the current decision kernel. Keep the
exhaustive test as the CI-facing proof (it already is — see
`exhaustive_all_reachable_inputs_satisfy_all_9_output_rules`). Revisit Kani
the day any rule input in `cms-security.yaml` grows a non-enumerable type
(string/id/timestamp beyond the current bounded int), and reuse this
spike's harness pattern (`kani::any` + `kani::assume` for input
preconditions + one proof per named rule) rather than re-deriving it.

## Reproduce

```
cd examples/cms/proof-spike
cargo test --release -- --nocapture   # exhaustive enumeration + timing data point
cargo kani                             # all 13 harnesses; exits nonzero because
                                        # the buggy-variant harness is *supposed* to fail
```

---

## Track D follow-up (2026-07-30): the boundary problem, fixed for the Rust side

Track D's episode log flagged a standing caveat on the Dafny→Go kernel:
"nothing forces the app to route through the kernel (the boundary
problem)". This crate now exposes `authz`, a wrapper API that turns that
convention into a compile error for the CMS app (`examples/cms/app/server`).
Full design rationale and code are in `src/authz.rs`'s module doc comment;
this section is the results writeup: what changed, what got re-verified,
and the actual compiler errors the "impossible by construction" claim rests
on.

### What was added (additive only)

- `Role`/`ArticleState` gained `Serialize`/`Deserialize` derives (so
  `app/server` can use these types directly instead of hand-rolling
  identical copies to serve over JSON) -- annotations only, no variant or
  match arm touched.
- `pub fn can_submit(is_author, active, state) -> bool` -- the
  draft→in_review workflow transition. Not one of the 10 YAML rules (it's
  a transition, not an access verb), so it's not part of `authorize`,
  `Perms`, or `ALL_RULES`, and it is **not** Kani-proven -- just exhaustively
  checked (16 points, `exhaustive_can_submit_matches_spec`). That's a
  deliberately weaker guarantee than the 9 proven rules, and this doc says
  so rather than blurring the distinction.
- `src/authz.rs`: the sealed `Grant<Op>` typestate, marker types
  `View`/`Edit`/`Submit`/`Publish`, `Identity`/`ArticleMeta` input structs,
  `DeniedRule`, and the one entry point, `require::<Op>(identity, meta) ->
  Result<Grant<Op>, DeniedRule>`. It calls `authorize()` (View/Edit/Publish)
  or `can_submit()` (Submit) internally -- the proven decision logic itself
  was **not modified**, only wrapped.
- `tests/compile_fail.rs` + `tests/compile-fail/*.rs` (trybuild): two
  compile-fail cases, described below.

**No existing function body in `lib.rs` (`authorize`, `authorize_by_id`,
`authorize_buggy_missing_active_check`, any `inv_*` predicate) was changed.**
Per the task brief's "if you touch the decision logic AT ALL, re-run both
[`cargo test --release` and `cargo kani`]" rule: this refactor is additive,
not a modification of the decision logic, but both were re-run anyway (see
"Regression" below) rather than relying on that distinction being airtight.

### What is now impossible by construction (type-enforced)

- A `Grant<Op>` can only be produced by `authz::require::<Op>`. Its one
  field is private and the struct is `#[non_exhaustive]` on top of that --
  no struct-literal syntax from another crate (or another module in this
  one) can build one.
- `Operation` (which selects what `require::<Op>` does) is sealed: only
  `View`/`Edit`/`Submit`/`Publish` implement it. An app author can't declare
  `struct MyOp;` and grant themselves a `Grant<MyOp>`.
- `Grant<Edit>` and `Grant<Publish>` are different types. Holding *a* grant
  is not enough; it must be the grant for the operation being performed.

### What remains convention (not type-enforced)

- **Identity freshness.** `require` decides correctly on whatever
  `Identity` it's handed; it cannot tell a live re-read from a stale cached
  snapshot. That's `AUTH_MODE`'s job in `app/server`, and it is a
  completely separate guarantee from "was the kernel consulted" -- see
  `app/README.md`'s `CHECK_AT_ACTION` correspondence table, unchanged by
  this refactor.
- **Discarding the `Result`.** Nothing stops a handler from calling
  `authz::require` and ignoring `Err(..)` (e.g. `let _ = ...;` instead of
  `?`). `app/boundary_lint.sh` is a textual, non-proof check for this and
  for direct `Role::*` comparisons reappearing in the four protected
  handlers.
- **Admin user-management** (`admin_deactivate`/`admin_demote`) is out of
  this refactor's scope (the task named view/edit/submit/publish) and still
  does its own `role != Role::Admin` check -- documented, not hidden, in
  `app/boundary_lint.sh` and `app/README.md`.

### The compile-fail demonstration

`tests/compile-fail/forge_grant_directly.rs` -- a caller in a separate
crate tries to construct a `Grant<View>` directly instead of calling
`require`:

```rust
use authz_spike::authz::{Grant, View};

fn main() {
    let _forged: Grant<View> = Grant {
        _op: std::marker::PhantomData,
    };
}
```

Actual `rustc` output (captured 2026-07-30, rustc 1.94.1, checked in at
`tests/compile-fail/forge_grant_directly.stderr`):

```
error[E0639]: cannot create non-exhaustive struct using struct expression
  --> tests/compile-fail/forge_grant_directly.rs:9:32
   |
 9 |       let _forged: Grant<View> = Grant {
   |  ________________________________^
10 | |         _op: std::marker::PhantomData,
11 | |     };
   | |_____^
```

`tests/compile-fail/wrong_grant_type.rs` -- a caller legitimately obtains a
`Grant<Edit>` (they really can edit the article) and tries to use it where
a `Grant<Publish>` is required:

```rust
let edit_grant: Grant<Edit> = require(identity, meta).unwrap();
do_publish(edit_grant); // expected `Grant<Publish>`, found `Grant<Edit>`
```

Actual `rustc` output (checked in at `tests/compile-fail/wrong_grant_type.stderr`):

```
error[E0308]: mismatched types
  --> tests/compile-fail/wrong_grant_type.rs:27:16
   |
27 |     do_publish(edit_grant); // expected `Grant<Publish>`, found `Grant<Edit>`
   |     ---------- ^^^^^^^^^^ expected `Grant<Publish>`, found `Grant<Edit>`
   |     |
   |     arguments to this function are incorrect
   |
   = note: expected struct `Grant<Publish>`
              found struct `Grant<Edit>`
note: function defined here
  --> tests/compile-fail/wrong_grant_type.rs:9:4
   |
 9 | fn do_publish(_grant: Grant<Publish>) {
   |    ^^^^^^^^^^ ----------------------
```

Both are wired into the normal `cargo test` run via `trybuild`
(`tests/compile_fail.rs`) -- a regression here means CI fails, not just "a
human noticed at review time". No `.stderr` file is checked in with an
expectation of matching future `rustc` versions byte-for-byte forever; it's
pinned to what this exact toolchain produces today and would need
regenerating (`TRYBUILD=overwrite cargo test`) if a future compiler changes
the wording -- the requirement being pinned down is "fails to compile", not
"produces this exact string".

### Regression (re-run both, as instructed)

```
$ cargo test --release
running 11 tests   (was 5 before this refactor: +4 authz-level parity
                     tests in authz.rs, +1 exhaustive can_submit test;
                     see authz.rs's `mod tests` and lib.rs's new test)
test result: ok. 11 passed; 0 failed

     Running tests/compile_fail.rs
running 1 test
test tests/compile-fail/forge_grant_directly.rs ... ok
test tests/compile-fail/wrong_grant_type.rs ... ok
test result: ok. 1 passed; 0 failed

$ cargo kani
Manual Harness Summary:
Verification failed for - kani_harness::kani_buggy_variant_violates_deactivated_does_nothing
Complete - 12 successfully verified harnesses, 1 failures, 13 total.
```

Identical outcome to the pre-refactor spike: all 9 finite-domain rule
harnesses + both feature/id-crossover groups still verify; the deliberate
buggy-variant harness still (correctly) fails. The kernel refactor did not
touch `authorize`/`authorize_by_id`/the `inv_*` predicates, and this run
confirms it didn't regress their proofs either.
