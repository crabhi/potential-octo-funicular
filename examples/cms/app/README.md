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
