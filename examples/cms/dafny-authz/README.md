# Track D — requirements → proven code (Dafny → Go)

Scoreboard row: `examples/cms/dafny-authz/` in `research/09-bridging-the-gap.md`.

Hypothesis: a verified decision kernel can be generated from the same
requirements (the 10 rules in `examples/cms/invariants/cms-security.yaml`)
and embedded in ordinary code — rung 5 of the assurance ladder, without
rewriting the app.

Falsifier that would have killed this: Dafny proof or Go compilation turns
out to be impractical here, or the kernel/app boundary leaks (a caller can
misuse the kernel and get the wrong answer anyway).

**Verdict: not falsified.** The proof completes, the Go build works, the
demo runs, and the buggy variant is correctly rejected. The falsifier that
*does* apply, and that this README states plainly below, is the
boundary problem: nothing forces a real caller to route decisions through
this kernel instead of its own ad hoc `if` statements. See "What's still
trusted."

## What's in this directory

| File | Role |
|---|---|
| `authz.dfy` | The decision kernel. `Authorize(role, isAuthor, active, state)` returns `Decision{view, edit, publish}`. The ten YAML rules and three feature guarantees are `ensures` clauses on it. |
| `authz_buggy.dfy` | Same `ensures` clauses, one seeded bug in the implementation (drops the `!active` guard on publish). Exists to prove the gate rejects it — see below. |
| `authz-go/` | `dafny build --target:go` output: `authz-go/src/{Authz,System_,dafny,authz.go}` (generated, do not hand-edit) plus `authz-go/src/demo/main.go` (hand-written, imports the generated `Authz` package). |
| `check.sh` | The whole gate: verify → build → run demo → verify-buggy-fails. Exits non-zero on any step's failure. |

No `DEADEND.md` — every install step in the task worked in this
environment (see "Install path," below); this is not a dead end.

## Install path that worked

1. `apt-get install -y dotnet-sdk-8.0` — the "download a release binary
   from GitHub" path was skipped; Ubuntu 24.04's own archive carries a
   .NET 8 SDK, which is all `dotnet tool install` needs.
2. `dotnet tool install --global dafny` → **Dafny 4.11.0**, no proxy/GitHub
   involved (it pulls from NuGet, which the environment reaches directly).
3. Dafny's CLI could not find Z3 4.12.1 next to the tool
   (`Z3 is not found...`). `apt-get install -y z3` gave **Z3 4.8.12**
   (Ubuntu's packaged version, older than Dafny's bundled expectation but
   still a valid SMT backend) — passed explicitly via
   `--solver-path "$(which z3)"`. Verification and the buggy-rejection both
   worked fine against this older Z3; if this breaks on a future Dafny
   version, pin a matching Z3 or download the version Dafny ships instead
   of the distro package.
4. `dafny build --target:go` needed `goimports`, which wasn't installed:
   installed with `go install golang.org/x/tools/cmd/goimports@latest`
   (resolves through the proxy's Go-module allowlist, not GitHub — no
   blocking).
5. The generated Go packages import each other by **bare** names
   (`import m_Authz "Authz"`, `import _dafny "dafny"`), which is
   old-style `GOPATH` layout, not a Go module. Building the demo therefore
   uses `GOPATH=.../authz-go GO111MODULE=off go build ./src/demo` rather
   than a `go.mod`. This is a property of Dafny's Go backend, not a
   workaround for this environment — anyone building `dafny build
   --target:go` output has to do the same.

Versions actually used, for reproducibility: Dafny 4.11.0+fcb2042,
Z3 4.8.12 (64-bit), .NET SDK 8.0.129, Go 1.24.7.

## The proof

```
$ dafny verify --solver-path "$(which z3)" authz.dfy
Dafny program verifier finished with 1 verified, 0 errors
```

One function, twelve `ensures` clauses (ten rules + two feature-only
duplicates kept for clarity — see the file), zero errors. Every clause
holds for *every* `(role, isAuthor, active, state)` combination the
precondition allows — not a sampled subset. That's the entire content of
rung 5: the decision logic was never run against test cases to check the
rules; the rules were proved of the logic.

### The ten rules, as `ensures` clauses

Each maps 1:1 onto a YAML invariant name (see comments in `authz.dfy` for
the full English sentence copied from the YAML):

| YAML invariant | `ensures` (abbreviated) |
|---|---|
| `inv_published_is_public` | `state == Published ==> d.view` |
| `inv_anonymous_published_only` | `role == Anonymous && d.view ==> state == Published` |
| `inv_draft_visibility` | `state == Draft && d.view ==> isAuthor \|\| role in {Editor, Admin}` |
| `inv_publish_staff_only` | `d.publish ==> role in {Editor, Admin}` |
| `inv_publish_from_review_only` | `d.publish ==> state == InReview` |
| `inv_edit_rights` | `d.edit ==> isAuthor \|\| role in {Editor, Admin}` |
| `inv_authors_edit_unpublished_only` | `d.edit && role == Author ==> state in {Draft, InReview}` |
| `inv_deactivated_does_nothing` | `!active ==> !d.edit && !d.publish` |
| `inv_archived_not_public` | `state == Archived && d.view ==> role != Anonymous` |
| `inv_anonymous_never_author` | `role == Anonymous ==> !isAuthor` |

Plus three **feature** guarantees not in the YAML — without them,
`Authorize` returning `Decision(false, false, false)` for every input
would satisfy all ten safety rules and verify "successfully" while being
useless. This mirrors the project's safety+features split used elsewhere
(07/08 ground rules):

- an active editor/admin can actually view a draft,
- an active editor/admin can actually publish an in-review article,
- an active author can actually view *and* edit their own unpublished
  article.

`session_ttl_minutes` from the YAML `variables` block is **not** modeled
here — it's a session-lifetime concern the YAML groups with the access
rules but that doesn't participate in any of the ten `implies(...)`
formulas. Out of scope for this kernel; noted so it isn't silently assumed
covered.

## Buggy variant is rejected (the gate demonstration)

`authz_buggy.dfy` is byte-for-byte identical in its `ensures` clauses. The
only change is in the implementation: the `publish` computation drops the
`if !active then false else ...` guard, so a **deactivated** editor or
admin can "publish" an in-review article.

```
$ dafny verify --solver-path "$(which z3)" authz_buggy.dfy
authz_buggy.dfy(82,4): Error: a postcondition could not be proved on this return path
   |
82 |     Decision(view, edit, publish)
   |     ^^^^^^^^

authz_buggy.dfy(43,36): Related location: this is the postcondition that could not be proved
   |
43 |     ensures !active ==> (!d.edit && !d.publish)
   |                                     ^

Dafny program verifier finished with 0 verified, 1 error
```

Line 43 is the `ensures` clause for `inv_deactivated_does_nothing` (see the
comment immediately above it in the file, line 40). Dafny's own error
message cites the clause's line/text, not the YAML-name comment above it
(comments aren't part of what it reports on) — `check.sh` greps for the
clause text and prints the cross-reference to the invariant name itself,
the same way a human reading the raw error would have to.

This is the whole point of rung 5 as a *gate*, not just a one-time proof:
a one-line regression that a code reviewer skimming an `if/else` chain
could plausibly miss is caught immediately and specifically, with no test
case required to trigger it.

## Compiling to Go and running the demo

```
$ dafny build --solver-path "$(which z3)" --target:go authz.dfy
Dafny program verifier finished with 1 verified, 0 errors
```

This regenerates `authz-go/src/{authz.go,Authz/,System_/,dafny/}` from the
just-verified source (Dafny re-verifies as part of `build`, so a build can
never emit code that failed verification). It does not touch the
hand-written `authz-go/src/demo/main.go`.

`authz-go/src/demo/main.go` builds a small runnable Go program that:

- imports the generated `Authz` package,
- constructs a table of scenarios including the three the task called out
  (deactivated-editor-publish → denied; anonymous-draft-view → denied;
  active-editor-draft-view → allowed) plus nine more covering the
  remaining rules,
- calls `Authz.Companion_Default___.Authorize(...)` for each,
- prints a table and exits non-zero if any scenario's actual output
  disagrees with the expected one.

Actual run:

```
Dafny-verified CMS authorization kernel — demo
====================================================================================================
scenario                                       view     edit     publish 
----------------------------------------------------------------------------------------------------
deactivated editor, publish in_review article  yes      no       no        [OK]
anonymous visitor, view a draft                no       no       no        [OK]
active editor, view a draft                    yes      yes      no        [OK]
anonymous visitor, view a published article    yes      no       no        [OK]
anonymous visitor, view an archived article    no       no       no        [OK]
admin, view an archived article                yes      yes      no        [OK]
author, edit own draft                         yes      yes      no        [OK]
author, edit own PUBLISHED article             yes      no       no        [OK]
author, try to publish own in_review article   yes      yes      no        [OK]
active editor, try to publish a DRAFT (not in_review) yes      yes      no        [OK]
active editor, publish in_review article       yes      yes      yes       [OK]
deactivated author, view own draft             yes      no       no        [OK]
====================================================================================================
All scenarios matched. (Recall: the ten YAML rules were proved for ALL inputs by
`dafny verify` before this program was ever built — this table is a sanity spot
check of the compiled artifact, not the source of assurance.)
```

Exit code `0`. This table is deliberately *not* the source of assurance —
it is 12 hand-picked points in a space `dafny verify` already covered
exhaustively. It exists only to show the compiled `.go` artifact behaves
like the proved `.dfy` source, i.e. that the Dafny→Go compiler didn't
introduce a translation bug of its own (a risk this project doesn't
independently verify — see below).

One surprising-until-you-check-the-rules result worth flagging: a
**deactivated** editor/author can still *view* an in-review/draft article
they'd normally see. `inv_deactivated_does_nothing` only restricts
`can_edit`/`can_publish` — the YAML says nothing about `can_view` for
deactivated accounts, so the proof doesn't force `view` to be gated on
`active`, and the kernel correctly does not add that restriction on its
own. If that's an oversight in the original stakeholder rules rather than
intentional, it's a requirements gap, not a kernel bug — and it's the kind
of gap this exercise is good at surfacing early, in the `ensures` list,
before it's live.

## `check.sh`

```
./check.sh
```

runs, in order: `dafny verify authz.dfy` → `dafny build --target:go` →
build+run the Go demo (fails the whole script if any scenario mismatches)
→ `dafny verify authz_buggy.dfy` (fails the whole script if this
*succeeds*, or if it fails for the wrong reason). Confirmed to exit 0 on
this environment with the tool versions listed above; exits non-zero on
any of the four sub-checks failing, with the failing step named.

## What's proven vs. what's still trusted

**Proven** (machine-checked, re-runs on every edit):

- All ten `implies(...)` formulas from `cms-security.yaml`, for every
  input in the finite domain `Role × bool × bool × ArticleState`
  (4 × 2 × 2 × 4 = 64 combinations, minus the ones the precondition
  excludes) — proven by SMT, not enumerated.
- The three feature guarantees, ruling out the trivial "always deny"
  non-solution.
- That a specific one-line regression (dropping an `active` check) is
  caught, and where.

**Still trusted (human-reviewed, not machine-checked):**

1. **The YAML → `ensures` translation itself.** The comment above each
   clause in `authz.dfy` is a direct copy of the YAML `description`, and
   the formula was translated by a person reading both side by side — but
   nothing *mechanically* ties `authz.dfy` to
   `examples/cms/invariants/cms-security.yaml`. If the YAML changes, a
   human has to notice and re-translate; there is no test or lint that
   flags drift between the two files. (A follow-up could parse the YAML
   `formula` strings and either generate the `ensures` clauses or diff
   against them — not attempted here.)
2. **The Dafny → Go translation.** `dafny build` re-verifies before
   emitting code, so the *Dafny* source that gets compiled is guaranteed
   to satisfy the ensures clauses. Whether the Go code Dafny's compiler
   emits is a faithful translation of that verified Dafny semantics is
   itself unverified — this project trusts the Dafny compiler as a
   correct (if unverified-by-us) tool, same as trusting `gcc` or `javac`.
3. **The kernel/app boundary — the falsifier this hypothesis names
   explicitly.** Nothing in this repository forces a real CMS handler to
   call `Authz.Companion_Default___.Authorize(...)` before serving a
   view/edit/publish request. A developer can add a new code path, a new
   role, or a shortcut ("admins always win") anywhere in the app and the
   proof says nothing about it — the proof is about the *function*, not
   about whether every caller in the app actually goes through it. That
   is a real, unresolved boundary problem, not a solved one: proving the
   kernel is necessary but not sufficient; someone still has to audit (or
   architecturally force, e.g. via a single call site / middleware) that
   every access decision in the app routes through this kernel. This
   directory does not attempt that integration — it stops at "the kernel
   embeds in ordinary Go and is provably correct on its own terms."
4. **The `isAuthor` precondition is a simplification.** Real "is this
   viewer the author of this specific article" is decided by a database
   join, not a boolean parameter. `requires role != Author ==> !isAuthor`
   encodes `inv_anonymous_never_author` and prevents nonsensical
   `(Anonymous, isAuthor=true)` calls, but a caller could still pass the
   wrong `isAuthor` for a *given* article (e.g. a bug in the join) and the
   kernel would happily authorize based on that wrong input. The proof is
   only as good as what the caller feeds it.
5. **`session_ttl_minutes`** (noted above) is out of scope entirely.

## Verdict for the Track D scoreboard row

**Not falsified; status: proof + Go embedding both work in this
environment.** Update `research/09-bridging-the-gap.md`'s Track D row
status from "in progress" accordingly, with the caveat carried forward
into the episode log: the open falsifier — "the kernel/app boundary leaks
(the caller can still misuse it)" — is real and unaddressed here by
design; this directory demonstrates the kernel can be built and proven,
not that a real app has been made to use it exclusively.
