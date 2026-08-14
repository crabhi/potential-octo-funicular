# DEVLOG — building Flowdeck under the rule-driven method

The raw developer-experience journal for this app, kept as the work
happened (2026-08-14). The distilled version is
`research/14-developer-experience.md`. Method under test: write the
tickets (TICKETS.md), translate them to one rule base, let the analyzer —
not a human — review every iteration. Predictions are recorded *before*
the run that tests them; wrong ones stay in the log (guardrail 7).

## Round 0 — setup (engine growth, before any taskboard file)

The vocabulary had no way to say "my team" or "assigned to me": tenancy
and assignment are *relations between the actor and the resource*, and the
engine only had `is_author`. Cost of the concept, paid once, generically
(no domain words):

- `actor_fields:` — per-user attributes (here: `team`) stored with the
  account;
- projection kind `actor_matches_field` — actor attribute == resource
  field, entering the vocabulary as a free boolean (`same_team`,
  `assigned_to_me`);
- fields can opt out of their automatic `has_` boolean (`{name: assignee,
  has: false}`) — every boolean doubles the situation space, and three of
  five `has_` bools would have been dead weight: 34,560 situations instead
  of 276,480. **The vocabulary is a budget.**

This is the third consecutive domain to cost exactly one missing generic
concept: receivables → time; taskboard → actor↔resource relations.

## Round 1 — first analyzer run (a load error, then a wrong prediction)

Wrote `rules.yaml` from the tickets in one sitting. First run:

    ConditionError: unknown variable 'actor.is_assignee'

Friction, honest: "is assignee" *reads* like an actor fact, but
projections live under `resource.*` (they are resource-relative). The typo
was a **load error with the variable named** — not a silently-false
condition (the grammar's whole point). Renamed the projection to
`resource.assigned_to_me`, which reads correctly in every rule that uses
it.

**Prediction (before the run):** `janitor_scope` (the TB-6 containment
deny) will be reported DEAD, like the receivables scope denies — bots that
own nothing are contained by default-deny alone.

Result: **prediction falsified.** All 18 rules effectual. The solver knew
what I didn't: `assignee_moves` had no role guard, so a task with
`assignee: dusty` would let the *janitor* start and submit work —
`janitor_scope` was refusing something real. (So was a task with
`assignee: anonymous` — see round 2.)

## Round 2 — the gate arrives: two real holes, two probe mistakes (0.18 s)

Wrote `safety.yaml` (13 ∀-properties, 8 ∃-witnesses, 2 gated lifecycle
entries) and `features.yaml` (5 scenarios, 36 steps) from the tickets.
Run: **4 findings.**

    FAIL S2_no_anonymous_access
         counterexample: {role: anonymous, action: start, state: backlog,
                          ... assigned_to_me: true ...}
         allowed by: assignee_moves
    FAIL S5_assignee_works
         counterexample: {role: admin, action: submit, state: in_progress,
                          ... assigned_to_me: false ...}
         allowed by: admin_oversees

Two genuine authorization bugs, each with the granting rule named:

- **S2**: anyone who can write the `assignee` field could hand start/submit
  to the anonymous public. I half-suspected this after round 1; the solver
  produced the exact situation.
- **S5**: I did *not* see this one coming. `admin_oversees` ("staff can
  see and support everything") quietly granted staff the team's work —
  TB-3 says only the assignee works. The broad allow read fine in the
  file; the ∀-check is what caught the interaction.

Fixes: role-guard `assignee_moves` (an allow should carry its audience)
and add the TB-3 deny `only_assignee_works` — which then upgraded a
feature step from `denied_by: default_deny` to a *named* refusal.

The other two findings were mine, not the rules':

    FAIL feat_kanban_flow: step 6 (mira delete): denied by
         history_is_immutable, expected nothing_is_deleted
    FAIL feat_janitor: step 6 (dusty edit): denied by
         history_is_immutable, expected janitor_scope

**When several denies overlap, the name you get is declaration-order.**
My probes tested delete/tamper on a *done* task, where the history rule
fires first. Moved each probe to the state where its deny is the only one
that matches (delete a backlog task; tamper mid-progress). Rule of thumb
learned: *place named-denial probes in the minimal state that triggers
them.*

## Round 3 — the containment deny dies on schedule (0.18 s)

    FAIL DEAD deny rule 'janitor_scope': it never refuses anything
         that another rule would have allowed

Round 1's prediction comes true — *after* the round-2 fix. Once
`assignee_moves` is role-guarded, no allow grants the janitor anything
beyond read/archive, so default-deny contains it and the deny is provably
useless. Deleted it; gate property S11 still **proves** containment over
every situation, which is the stronger statement anyway. The receivables
observation is now a live diagnostic: **the dead-rule check tells you
which containment regime you are in, and tracks it as the allows change.**

## Round 4 — PASS (0 findings)

18 rules (11 deny, 7 allow), 13 safety + 8 possibility properties, 5
feature runs, 34,560-situation space. Analyzer wall-clock per round:
**~0.18 s.** Author wall-clock, tickets to green gate: about an hour,
most of it *writing* the two YAML files, almost none of it debugging.

## What the loop feels like (kept honest)

- The unit of work is a sentence, not a function. Every edit was a
  ticket-shaped stanza; there was never a moment of "now write the
  handler that enforces this".
- Review latency is effectively zero. Four rounds at 0.18 s. The finding
  arrives with the situation *and* the granting/blocking rule — no
  debugger, no log-diving; the fix was obvious from the finding text every
  single time.
- The analyzer caught two authorization bugs (S2, S5) that type systems
  and tests would both have missed — nobody writes the test where the
  task is assigned to the anonymous user.
- The gate is where the thinking lives. Writing `safety.yaml` forced the
  TB-3 question "may staff work a task?" that the rules alone let me
  fudge. ∀-properties are the design review.
- Frictions, real: projection naming (resource-vs-actor namespace);
  deny-order sensitivity of `denied_by` names; and `edit` cannot see
  *proposed* values, so "title can never be emptied later" is not
  expressible — S3 guards creation only. Vocabulary gaps fail loud
  (load error), semantic gaps like the edit one fail silent — you must
  notice them yourself. That is the sharpest DX edge found today.
- One entity per rule base held fine for a kanban app; comments or
  checklists would force the relations question (note 13's known limit).

## Round 5 — the app exists without further programming

`app.py` starts the generic engine with `--ui` on this ruleset and seeds
demo data **through the rules over HTTP** (a seed that violates policy
cannot exist). Board, forms, buttons, named 403 banners, and the /ui/rules
page all derive from rules.yaml. Zero lines of Flowdeck-specific UI or
handler code were written for this application. Live verification:
`live_demo.py` replays the five frozen features over real HTTP and runs
the visibility probe (the board equals the read rule) — see check.sh.
