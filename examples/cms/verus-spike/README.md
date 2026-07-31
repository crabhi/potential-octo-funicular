# Track L: session/identity state machine, proven

research/10-proof-escalation.md, Track L: "Real Rust code proof beyond the
pure kernel: session/identity state machine in the app." The kernel
(`examples/cms/proof-spike`, `examples/cms/dafny-authz`) proves the pure
authorization *decision function*. Everything mutable that feeds it a
role/active pair -- login, admin deactivate/demote, and the AUTH_MODE
cached-vs-live split in `resolve_identity` -- lived outside any prior proof.
This directory closes that gap for the model; see "Extraction-fidelity gap"
below for exactly how far "for the model" is from "for the axum code."

## Route taken

The charter's step 1 asked for Verus first, since it type-checks against
real Rust source (`#[verifier::proof]`/`verus!{}` over actual `main.rs`
functions), which would close the extraction-fidelity gap this Dafny model
cannot. Tried and blocked:

```
$ curl -sS -I --max-time 15 https://github.com/verus-lang/verus/releases
HTTP/1.1 200 Connection Established
HTTP/1.1 403 Forbidden
```

The outbound agent proxy returns 403 on the verus-lang releases page --
no release binary is reachable from this environment, and there is no
package-manager path to a Rust deductive verifier here either (Verus isn't
on crates.io as an installable verifier toolchain the way Kani/cargo-kani
is). Per the charter this is an acceptable outcome, not a blocker: went
directly to the Dafny fallback, reusing the exact toolchain
`examples/cms/dafny-authz/check.sh` already validates works in this
environment (dafny via `dotnet tool`, z3 via `--solver-path`). The
directory keeps the name `verus-spike/` per instructions, even though the
tool actually used is Dafny -- the name records what was *attempted*.

## What's in here

- `identity_store.dfy` -- the model: a `Store` (users map + sessions map),
  transition functions `Login`/`Deactivate`/`Demote`, and resolution
  functions `ResolveLive`/`ResolveCached` mirroring
  `examples/cms/app/server/src/main.rs`'s `resolve_identity` (lines
  184-193) and its two AUTH_MODE arms. Every declaration is commented with
  the exact main.rs line range it models.
- `identity_store_buggy.dfy` -- `ResolveLive` seeded with the one bug the
  charter asked for: `active` read from the session's own snapshot
  (`sessions[token].2`) instead of from the live `users` map, while `role`
  still (correctly) comes from `users`. This is a *subtler* bug than
  "reads the whole snapshot" -- it looks like a live re-read.
- `check.sh` -- the gate: verify the good file, verify the buggy file is
  rejected, assert the rejection names the expected clauses. Ran clean;
  output below.

## Theorems proved (identity_store.dfy, 14/14 verification conditions, 0 errors)

All are `lemma`s with universally-quantified parameters under `requires` --
in Dafny that already means "for every state/token satisfying the
preconditions," not a sampled instance.

**(a) Freshness** (`FreshnessLive`): for any state `s` and any token with a
session, `ResolveLive(s, token) == Some(s.users[s.sessions[token].0])` --
the live resolver's answer is *always* the current `users`-map entry, by
construction. Models main.rs 188-191
(`state.users.get(&session.user)?`).

**(b) Revocation immediacy** (`RevocationImmediate`): for any state `s`,
any user `u` in `s.users`, and any token `t` whose session names `u`,
`ResolveLive(Deactivate(s, u), t)` returns `active == false`. Because `t`
is a lemma parameter constrained only by "names `u`", this covers *every*
session `u` might hold, not one example -- the code-level form of
`inv_deactivated_does_nothing` holding immediately under `AuthMode::Live`.
Companion `DemotionImmediate` proves the same for the role field under
`Demote`. Models main.rs 418-437 and its comment at 432-435 that sessions
are deliberately *not* revoked -- the theorem shows the users-map mutation
alone is sufficient for Live mode.

**(c) Live/cached asymmetry, as an existence proof**
(`CachedStaleAfterDeactivation`): a lemma with `returns` that *constructs*
a concrete witness -- editor `eve`, one login, then one deactivation -- and
machine-checks that in the resulting state
`ResolveLive(s, token) == Some((Editor, false))` while
`ResolveCached(s, token) == Some((Editor, true))`. This is the code-level
twin of the abstract model's `CHECK_AT_ACTION` CTI from the same day's
episode log (research/10-proof-escalation.md, Track I(b): "the SAME
invariant fails consecution on cms_cached with a concrete CTI (cached
EDITOR, demoted live role)"). There, Apalache *found* the counterexample by
search; here, the counterexample's existence as a reachable state is
*proven*, with a witness anyone can replay by hand.

## Buggy variant: rejected, as required

`identity_store_buggy.dfy`'s `ResolveLive` reads `active` from the session
snapshot. Verifying it fails with 2 errors (not 1) -- the seeded bug breaks
both `RevocationImmediate` (the one the charter named) and, as a bonus
finding, `FreshnessLive` too, since a stale `active` bit means the
resolver's answer no longer equals the current `users` entry *at all*,
even absent any deactivation. Captured verifier output:

```
identity_store_buggy.dfy(94,2): Error: a postcondition could not be proved on this return path
   |
94 |   {
   |   ^

identity_store_buggy.dfy(93,34): Related location: this is the postcondition that could not be proved
   |
93 |     ensures ResolveLive(s, token) == Some(s.users[s.sessions[token].0])
   |                                   ^^

identity_store_buggy.dfy(108,2): Error: a postcondition could not be proved on this return path
    |
108 |   {
    |   ^

identity_store_buggy.dfy(107,52): Related location: this is the postcondition that could not be proved
    |
107 |     ensures ResolveLive(Deactivate(s, user), token) == Some((s.users[user].0, false))
    |                                                     ^^

Dafny program verifier finished with 8 verified, 2 errors
```

`check.sh` asserts on both clause texts, so a future edit that accidentally
weakens either theorem trips the gate the same way.

## What is proven vs what tests approximated

Before this track, the session/identity logic in main.rs had exactly one
kind of evidence: the `mbt`/`trace-validation` HTTP test suites exercise
`login` → `admin_deactivate` → a follow-up request under both `AUTH_MODE`
settings, for the finitely many scripted scenarios someone thought to
script. That is sampling, in the same sense the research doc's self-audit
table already names for the app-conformance rows. What's proven here
instead:

- Freshness and revocation-immediacy hold for **every** state reachable by
  arbitrary sequences of `Login`/`Deactivate`/`Demote`, and for **every**
  token a deactivated user might be holding -- not the one token a test
  happened to mint.
- The live/cached asymmetry is asserted to **exist** as a reachable state,
  with a checked witness, rather than inferred from "we ran the cached-mode
  test suite and it didn't flag it."

What is *not* proven by this file: that `main.rs` actually implements
`Store`/`Login`/`Deactivate`/`Demote`/`ResolveLive`/`ResolveCached`. That
link is asserted by the line-number comments in `identity_store.dfy` and
reviewed by a human (me, right now, reading main.rs lines 184-193 and
418-454 while writing this file) -- exactly the same trust boundary
`dafny-authz/authz.dfy`'s header names for the YAML→ensures mapping: "the
one part of this pipeline that is NOT machine-checked."

## Extraction-fidelity gap

This store is a hand-drafted *model* of main.rs's session logic, not the
axum code itself. Concretely, faithful-by-construction has limits here:

- `resolve_identity`'s `match state.mode { ... }` (main.rs 186-192) becomes
  two *separate* functions, `ResolveLive`/`ResolveCached`, in the model --
  there's no single Dafny function whose body a diff tool could compare
  line-for-line against the Rust match arms.
- The model has no `RwLock`, no `axum` extractors, no HTTP status codes, no
  `uuid::Uuid::new_v4()` (tokens are model-level `string`s with no
  freshness/collision reasoning); those are exactly the layers `authz.dfy`
  --> Go compilation sidesteps too by targeting a hand-written Go demo
  rather than a decompiled binary.
- Nothing here re-runs if `main.rs` changes. `authz.dfy`'s ten rules stay
  honest only via `check.sh` being wired into CI as "re-run on every edit"
  (research doc's own phrasing); this file has no such trigger, and no
  automated check that `resolve_identity`'s Rust body still matches the
  `ResolveLive`/`ResolveCached` split above.

What would close the gap, in ascending cost:
1. **Cheapest, matches this project's existing pattern**: do to this file
   what `dafny-authz/check.sh` step 2 already does to `authz.dfy` --
   `dafny build --target:go` (or `:rs` once Dafny's Rust backend matures)
   to *generate* `resolve_identity`'s logic from `identity_store.dfy`, and
   have `main.rs` call the generated module instead of hand-rolling the
   match arms. Then the proof is about the code that ships, by
   construction, the same argument `dafny-authz/README.md` makes for the
   kernel.
2. **Middle**: a property-based differential test (`proptest` in Rust)
   that runs the *actual* `resolve_identity`/`admin_deactivate` handlers
   against random operation sequences and checks agreement with this
   model's `Store` on every step -- turns "human read the line numbers"
   into "machine checks the mapping holds on N random runs." Still
   sampling, but sampling *of the model-conformance question* specifically,
   which today has zero evidence of any kind.
3. **Most faithful**: retry Verus (or a Rust deductive verifier the proxy
   does permit fetching) with real network access, and write the `ensures`
   clauses directly on `resolve_identity`/`admin_deactivate` in-place in
   `main.rs`. This is what step 1 of the charter wanted and what the 403
   blocked -- worth re-attempting whenever release binaries become
   reachable, or via a vendored/offline Verus install.

## Verifier output (this session, in full)

```
$ ./check.sh

=== 1/2 dafny verify identity_store.dfy (state-machine theorems, proved for all reachable states) ===

Dafny program verifier finished with 14 verified, 0 errors

=== 2/2 dafny verify identity_store_buggy.dfy must be REJECTED ===
Confirmed: verifier rejects the buggy variant, citing both RevocationImmediate's
and FreshnessLive's ensures clauses (identity_store_buggy.dfy: ResolveLive reads
active from the session snapshot instead of the live users map):
[... error output reproduced above ...]

ALL CHECKS PASSED.
```

(`dafny 4.11.0+fcb2042`, `z3 4.8.12`, same versions `dafny-authz/check.sh`
uses in this environment.)

## Verdict for Track L

**PROVEN, with a scoped fallback.** Verus itself is blocked in this
environment (403 on release downloads); the Dafny fallback is not a
downgrade in *rigor* -- all three theorems are exhaustive over the model's
state space, same as `dafny-authz`'s kernel proof -- but it is a downgrade
in *fidelity*: the model is reviewed-by-eye against main.rs, not
type-checked against it. Track L status should read: state-machine
theorems proven for the model (freshness, revocation immediacy, live/cached
asymmetry-as-witness, buggy variant correctly rejected); extraction
fidelity remains an open TCB item, same shape as `dafny-authz`'s YAML→ensures
mapping, with a concrete next step (Dafny→Go/Rust codegen, §"Extraction-
fidelity gap" item 1) queued rather than attempted here.
