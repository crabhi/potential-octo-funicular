# Demo CMS — real-system rung of the worked example

This is the "does it actually hold against a running system" step for the
formal security invariants in `../invariants/cms-security.yaml`. A real
Rust/axum HTTP API enforces (or, deliberately, fails to enforce) those
invariants, and a real Python/Hypothesis harness drives it over real HTTP
and checks the results — no mocks.

A sibling Quint model, `../model/cms.qnt`, is where those same invariants
get model-checked at the specification level (see below for the
correspondence). This directory doesn't read or require that model — it's
mentioned only to place this prototype in the pipeline: formal model -> this
conformance harness against a real server.

## What it shows

- The 4 roles, the article lifecycle (`draft -> in_review -> published`,
  plus `archived`), and every access-control invariant in
  `cms-security.yaml` enforced by a real server, with every denial
  returning `403` and a JSON body naming the invariant it protects —
  e.g. `{"error": "inv_draft_visibility"}`. That name is the
  machine-readable counterexample hook the harness asserts against.
- A **property-based conformance suite** (`harness/test_policy.py`) that
  exercises the server over HTTP in `AUTH_MODE=live` and expects every
  check to pass.
- **One deliberately reproducible authorization race**
  (`harness/test_stale_session_race.py`): a stale/cached session token
  that keeps authorizing actions after the acting user has been demoted
  or deactivated — a real check-then-act (TOCTOU) bug, reproduced on
  demand via the `AUTH_MODE` knob, not found by chance.

## The `AUTH_MODE` knob <-> the formal model's `CHECK_AT_ACTION`

The formal model (`../model/cms.qnt`) presumably parameterizes whether
authorization state is re-checked at the moment of the action or trusted
from an earlier snapshot — call that constant `CHECK_AT_ACTION`. The
server's `AUTH_MODE` env var is the runtime analogue:

| `AUTH_MODE` | Behavior | `CHECK_AT_ACTION` analogue |
|---|---|---|
| `cached` (default) | The session token captures the user's role + active flag **at login time**; every later request trusts that snapshot. This is the realistic "stale JWT" design most real APIs actually ship. | `false` — checked once, at session-issue time |
| `live` | Every request re-reads the acting user's **current** role/active flag from shared state before deciding. | `true` — checked at the moment of the action |

Everything else about the server (routes, state machine, invariant names)
is identical between the two modes; only `resolve_identity()` in
`server/src/main.rs` branches on the mode. This isolates the TOCTOU bug
class to exactly the one function it belongs in.

## Invariant -> endpoint-check mapping

| Invariant (`cms-security.yaml`) | Enforced at | Violated by (race demo) |
|---|---|---|
| `inv_published_is_public` | `GET /articles/:id` (published always visible) | — |
| `inv_anonymous_published_only` | `GET /articles/:id` (anonymous branch) | — |
| `inv_draft_visibility` | `GET /articles/:id` (draft/in_review branch) | — |
| `inv_archived_not_public` | `GET /articles/:id` (archived branch) | — |
| `inv_anonymous_never_author` | `POST /articles` (requires a session; anonymous can't create) | — |
| `inv_edit_rights` | `PUT /articles/:id` | — |
| `inv_authors_edit_unpublished_only` | `PUT /articles/:id` (author-role branch) | — |
| `inv_publish_staff_only` | `POST /articles/:id/publish` (role check) | yes, via `AUTH_MODE=cached` + demote |
| `inv_publish_from_review_only` | `POST /articles/:id/publish` (state check) | — |
| `inv_deactivated_does_nothing` | every mutating endpoint's `active` check | yes, via `AUTH_MODE=cached` + deactivate |

## Layout

```
app/
  server/            Rust axum API (in-memory state, tokio RwLock, no DB)
  harness/            Python venv + hypothesis/requests/pytest suite
    test_policy.py            property tests, AUTH_MODE=live
    test_stale_session_race.py  the race, self-managed cached+live instances
    cms_client.py              thin HTTP client shared by both test files
    server_control.py          spawn/kill helper (each race scenario gets
                                a fresh process; in-memory state has no
                                other reset mechanism)
  run_demo.sh
```

## How to run

```bash
./run_demo.sh
```

Builds the server, provisions `harness/.venv` if missing, starts the
server in `AUTH_MODE=live` on port 3100, runs `test_policy.py` (expect all
5 green), stops that instance, then runs `test_stale_session_race.py`
(which starts and tears down its own `cached`- and `live`-mode instances
per scenario), and prints a summary. Idempotent — safe to re-run; kills
anything it started (and anything left over from an interrupted previous
run) on exit.

To run pieces individually:

```bash
cd server && cargo build && AUTH_MODE=live ./target/debug/cms-server &
cd ../harness
.venv/bin/python3 -m pytest test_policy.py -v
.venv/bin/python3 -m pytest test_stale_session_race.py -v -s   # manages its own servers
```

## Findings

- The **live-mode policy suite is fully green**: 5/5 checks pass —
  anonymous visibility, cross-author edit protection, publish-from-review
  enforcement, and both post-demote and post-deactivate publish refusals
  all hold when the server re-checks state at the moment of action.
- The **race is 100% reproducible in cached mode, every run**: a session
  token issued while eve was an active editor keeps successfully
  publishing after she's demoted to author, and separately after she's
  deactivated — both go through as `200 published`, a live violation of
  `inv_publish_staff_only` / `inv_deactivated_does_nothing` respectively,
  not a probabilistic race — the bug is structural (the token simply never
  gets re-checked), so it reproduces deterministically rather than needing
  many trials.
- The **same two sequences are refused with 403 in live mode**, each
  naming the specific invariant it protects (`inv_publish_staff_only`,
  `inv_deactivated_does_nothing`), confirming the fix is exactly
  "check at the point of action" and nothing else needs to change.
- Each race scenario runs against its own freshly spawned server process.
  The in-memory, no-database state has no reset endpoint, and demoting or
  deactivating eve is a one-way trip within a running process — reusing
  one process across scenarios caused exactly the kind of test-order
  interference this note is warning readers about elsewhere: an earlier
  scenario's leftover state silently changed *why* a later assertion
  passed. That's not itself a violation of any `inv_*` rule — it is
  test-isolation hygiene the harness earns by spawning fresh processes
  per scenario, the same way P3 gives each stateful/concurrent test suite
  a clean schema.

## Track D follow-up (2026-07-30): the authorization kernel is now load-bearing, mechanically

Track D's episode log (`research/09-bridging-the-gap.md`) named a standing
caveat on the Dafny→Go kernel: "nothing forces the app to route through the
kernel (the boundary problem)". This app is the fix for that, on the Rust
side. `get_article`, `edit_article`, `submit_article`, and `publish_article`
no longer contain a single `if role == ...` / `if state == ...` access
check -- every one of them now calls
`authz::require::<Op>(identity, meta)?` from the sibling `proof-spike`
crate (now a real library dependency, `authz_spike`, not just a Kani
sandbox) and only proceeds on `Ok`. `Role` and `ArticleState` themselves
are now the kernel's types (`use authz_spike::{Role, ArticleState}`), not
look-alike copies.

### What is type-enforced (a compiler error, not a convention)

`authz_spike::authz::Grant<Op>` is a sealed capability token: it has one
private field, the struct itself is `#[non_exhaustive]`, and the only
function that can produce one is `authz::require::<Op>`. Concretely, in
this codebase, that means:

- A handler cannot skip the authorization check and still compile, because
  there's no local `if` to skip *around* anymore -- the check **is** the
  only route to a `Grant<Op>`, and the handler needs one before it touches
  protected state.
- A handler cannot reuse "I checked something" for the wrong operation:
  `Grant<Edit>` and `Grant<Publish>` are different types, so a `Grant`
  obtained for editing cannot be passed anywhere a `Grant<Publish>` is
  required. See `proof-spike/README.md`'s "Track D follow-up" section for
  the actual `rustc` errors this produces (`E0639` for forging a `Grant`
  directly, `E0308` for using the wrong `Grant<Op>`), captured from a
  `trybuild` compile-fail test that runs as part of `cargo test` in
  `proof-spike/`.

### What remains convention (documented, not type-enforced)

- **A handler could call `authz::require` and discard the `Err`** (skip the
  `?`). Nothing in the type system stops that. `boundary_lint.sh` (new,
  `app/boundary_lint.sh`) is a textual belt-and-suspenders check: it greps
  `server/src/main.rs` and asserts that `get_article`/`edit_article`/
  `submit_article`/`publish_article` each (a) call `authz::require` and (b)
  contain no direct `Role::*` comparison of their own. Run it directly:

  ```
  $ ./boundary_lint.sh
  boundary_lint: OK -- get_article/edit_article/submit_article/publish_article contain no direct Role::* comparisons and each calls authz::require
  boundary_lint: (admin_deactivate/admin_demote intentionally not scanned -- out of refactor scope, see README)
  ```

  This is pattern matching over source text, not a proof: a rewrite that
  keeps a call to `authz::require` in the source while defeating its
  result would not be caught. The `Grant<Op>` typestate above is the actual
  guarantee; this script is the "and also we checked" layer research/09
  asked for.
- **`admin_deactivate`/`admin_demote`** (deactivating or demoting a user)
  are deliberately *out of scope* for this refactor -- the task named
  view/edit/submit/publish, and neither admin action nor its "only active
  admins may do this" rule is part of the proven `authorize()`/`Perms`
  decision core (there's no `inv_*` YAML rule for "who may demote"; the app
  reuses `inv_publish_staff_only`'s name for the 403, which was already a
  slight abuse of that rule's vocabulary before this refactor and is
  unchanged by it). Both handlers still do their own
  `if !active || role != Role::Admin` check. `boundary_lint.sh` does not
  scan them and says so in its own comments -- this is the one place left
  in `main.rs` with a raw role comparison, by design and on the record.
- **Identity freshness is untouched, on purpose** -- see the next section.

### The stale-identity race is untouched, and that's correct

The kernel decides correctly on whatever `Identity` it is handed. It has no
way to distinguish "this role/active snapshot was just re-read from live
state" from "this role/active snapshot is a minute-old cached session
token" -- and it shouldn't try to; that's a different guarantee than
"was the access-control decision computed correctly for these inputs".
`AUTH_MODE` (`resolve_identity` in `main.rs`) is entirely responsible for
*which* snapshot the kernel receives; the kernel's job starts only once
that snapshot exists. This is exactly the correspondence already
documented above: `AUTH_MODE=cached` ↔ `CHECK_AT_ACTION=false` (checked
once, at session-issue time) vs. `AUTH_MODE=live` ↔ `CHECK_AT_ACTION=true`
(checked at the moment of the action). Refactoring the *decision* into a
sealed kernel does nothing to move that knob -- it's still the one function
(`resolve_identity`) that branches on it, completely outside `authz`.

Confirmed empirically, not just argued: the regression run below still
reproduces the cached-mode race 2/2 (stale token published after demote,
stale token published after deactivate) and still shows live mode refusing
the identical sequence 2/2, naming the same two invariants
(`inv_publish_staff_only`, `inv_deactivated_does_nothing`) as before the
refactor. The kernel didn't (and structurally couldn't) fix a bug in
*which identity gets checked* -- it only guarantees *that* checking
happens and *what* the checked decision is.

### A minor, deliberate behavior change (untested edge case)

Pre-refactor, `edit_article`/`submit_article`/`publish_article` checked
"is there a valid, active session" *before* fetching the target article --
so a request from a deactivated user against a nonexistent article ID
returned `403 inv_deactivated_does_nothing`, not `404`. Post-refactor, all
four protected handlers fetch the article first (a `404` on a bad ID
always wins), matching `get_article`'s pre-existing order exactly. This
harmonizes the four handlers onto one consistent rule ("does the resource
exist" is answered before "are you allowed to act on it") and was necessary
because the kernel's `ArticleMeta { state }` requires knowing the article's
state before a decision can be requested. No test in `harness/` exercises
this specific combination (inactive user + nonexistent article), so nothing
in the harness's observed behavior changed; this is called out here for
completeness, not because anything failed.

### Regression: `run_demo.sh` is still green

```
================= SUMMARY =================
policy checks passed (live mode):      5/5
violations reproduced (cached mode):    2/2
refusals confirmed (live mode, race):   2/2
=============================================
DEMO OK
```

Identical to the pre-refactor numbers. `proof-spike`'s own suite was also
re-run (see `proof-spike/README.md` "Track D follow-up" → "Regression"):
`cargo test --release` (11 tests, including the new compile-fail cases) and
`cargo kani` (12 successful / 1 expected failure, same as before) both
green -- the kernel refactor did not touch, and did not break,
`authorize()`/the 9 proven rules.

## Deviations from the brief

- The brief describes the race scenarios as pytest functions reading a
  `CMS_MODE` env var against an externally-managed server. In practice
  demoting/deactivating eve permanently mutates the one seeded editor
  account, so running both the demote-variant and deactivate-variant
  scenarios against the *same* running process makes the second
  scenario's outcome ambiguous (already-demoted-or-deactivated eve from
  the first scenario). The brief's own wording — "starts (or expects) the
  server" — allows this: `test_stale_session_race.py` spawns and tears
  down its own server process per scenario (`server_control.py`) instead
  of depending on an externally started one. `run_demo.sh` still starts
  and stops a `live`-mode instance itself for the policy suite, exactly as
  specified.
