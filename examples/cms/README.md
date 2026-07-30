# Worked example: a CMS guarded by formal specification

A realistic end-to-end walkthrough of the project's workflow on a domain
everyone knows: a content management system with **user roles** (anonymous,
author, editor, admin), **draft articles**, a review/publish lifecycle, and
**public access** rules. Every artifact here actually runs — the outputs
below are real.

The security requirements start as ten stakeholder sentences ("a draft is
visible only to its author, editors, and admins", "only editors and admins
may publish", "archived articles are not publicly accessible", ...) and
flow through the three rungs of the pipeline:

```
invariants/   typed rules           -> P2 oracle: contradictions, dead features
model/        Quint state machine   -> model checker: authorization races
app/          Rust API + harness    -> the same rules enforced & tested live
```

## Rung 1 — the rules themselves (`invariants/`, uses prototype P2)

`cms-security.yaml` holds the ten base rules; each `description` is the
original stakeholder sentence, each `formula` its reviewed translation.

**Story A — two tickets collide.** Security files SEC-482 ("sessions must
expire within 15 minutes", SOC2 finding). Editorial UX files CMS-1201
("sessions must last at least an hour, we lose half-written reviews").
Both get translated and added (`cms-conflict.yaml`). The oracle:

```
$ oracle check cms-conflict.yaml
Verdict: IMPOSSIBLE
Unsat core (minimal conflicting invariants):
  - inv_sec_sessions_expire_fast:  SECURITY: ... within 15 minutes (SEC-482)
  - inv_ux_editor_sessions_long:   EDITORIAL UX: ... at least an hour (CMS-1201)
```

Twelve rules in the file; the solver names exactly the two that cannot
coexist — before a line of session code is written or reviewed.

**Story B — a rule silently kills a feature.** Legal adds LEG-77:
"unpublished material must not be accessible to anyone except the person
who wrote it" (`cms-strict-privacy.yaml`). The rule set stays CONSISTENT —
nothing contradicts. But ask whether the editorial workflow still exists:

```
$ oracle claim cms-strict-privacy.yaml \
    --claim 'viewer_role == "editor" and article_state == "draft"
             and (not viewer_is_author) and can_view'
Verdict: INVALID   (invariants entail the negation of the claim)
```

Under the combined rules, **an editor can never see anyone else's draft**
— review-before-publish is dead, yet every individual rule looks
reasonable. This is the "unexpected outcome" query from the project brief,
answered by a solver instead of a production incident.

## Rung 2 — behavior over time (`model/`, Quint — same style as P1)

Single-state rules can't see races. `model/cms.qnt` adds time: sessions
that **cache the user's role at login**, admin actions (demote, deactivate)
that run concurrently, and a draft → in-review → published lifecycle.

One constant, `CHECK_AT_ACTION`, selects the design:
- `cms_live` — every request re-checks the live role/active flag.
- `cms_cached` — requests trust the session snapshot (the realistic
  stale-JWT / cached-claims design).

```
$ ./check.sh
cms_live    simulate 20k traces: clean      verify (Apalache, 10 steps): NoError
cms_cached  simulate: VIOLATION in <1s      verify: counterexample in ~7s
```

The found trace (seed in `check.sh`): an author logs in; the admin
**deactivates the account**; the still-open session submits content anyway
— forbidden by the live policy (`inv_deactivated_does_nothing`). Other
seeds find the editor variant: log in as editor, get demoted, publish
anyway. Same class as prototype P3's TOCTOU finding: **check-then-act with
a stale snapshot** — here it's authorization instead of schema flags.

The ghost variable pattern makes this checkable with one invariant:
`lastActionOk` — "every committed action was permitted by the live policy
at the moment it committed."

## Rung 3 — the real system (`app/`)

A small Rust (axum) CMS with exactly these roles and lifecycle, plus a
Python property-test harness. The `AUTH_MODE=cached|live` env var is the
implementation twin of the model's `CHECK_AT_ACTION`:

- in `live` mode the policy suite must be green (anonymous never reads a
  non-published article, authors can't touch others' drafts, publish only
  from review, deactivated/demoted accounts lose access immediately);
- in `cached` mode the harness **reproduces the model's counterexample over
  real HTTP**: eve's pre-demotion token still publishes.

403 responses name the violated invariant (`inv_draft_visibility`, ...) —
the machine-readable counterexample hook for a future agent loop (P4).

See `app/README.md` for run instructions and results.

## What a developer's day looks like in this workflow

1. Write the requirement in English, in a ticket, as always.
2. An LLM drafts the formal rule; you review it next to your sentence.
3. `oracle check` before merge: conflicts surface as named rule pairs,
   dead features as INVALID claims — at review time, not in production.
4. Where time/concurrency matters (sessions, caching, lifecycle), the rule
   graduates into the Quint model; the checker hunts for interleavings.
5. The app enforces the same named rules; property tests + (later) an
   agent gate keep implementation and spec from drifting.
```
ticket -> rule -> oracle -> model -> code+tests    (same invariant names
                                                    at every rung)
```
