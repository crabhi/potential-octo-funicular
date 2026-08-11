# Rule-driven CMS: the whole service, from the ground up, as rules

Every other artifact in this repo models **one facet** of a system (a
migration protocol, an authz kernel, a session machine) and verifies it
*next to* the code. This example asks the question the other way around:
if a human were building a full web service — a CMS — from scratch today,
with LLM agents and solvers at hand, **is "formal methods" even the right
framing? What if the service is a rule-based system?**

Here the developer does not write handlers and then specs about them.
They write **one artifact — the rule base — and that artifact IS the
application**:

```
 rulesets/cms/rules.yaml     the CMS: roles, lifecycle, 14 allow/deny rules   130 lines
 rulesets/cms/safety.yaml    FROZEN gate: 9 ∀-props, 6 ∃-props, 1 lifecycle    95 lines
 rulesets/cms/features.yaml  FROZEN gate: 5 end-to-end scenarios               88 lines
 ──────────────────────────────────────────────────────────────────────────────
 engine/ + analysis/         generic, domain-free, reusable                 ~1010 lines
```

The engine (HTTP server, SQLite store, decision function) contains **no
domain words** — grep it for `article`, `publish`, `editor`: they occur
only in docstrings. The proof that it's generic is executable: ruleset
`tickets/` is a *different service* (support tickets) served and analyzed
by the same engine, byte for byte.

```
./check.sh        # everything below, one command (needs python3; pip-installs pyyaml+z3)
```

## The architecture

```
                    rules.yaml  (the program — editable, per change)
                        │
        ┌───────────────┴───────────────────┐
        ▼                                   ▼
  engine/  (generic)                  analysis/analyze.py  (generic)
  every request:                      every rule-base change:
    lifecycle legality                  dead rules        (Z3, per rule)
    → rule decision                     safety            (Z3, ∀ situations)
    → act                               possibility       (Z3, ∃ witness)
  403 = {"denied_by": rule_id}          lifecycle         (rules × states)
        ▲                               feature runs      (pure replay)
        │                                   ▲
        └───────── same decision ───────────┘
                   function                 │
                    safety.yaml + features.yaml  (the gate — FROZEN)
```

One condition grammar, two backends: each rule's `when` is parsed once and
then *both* evaluated on live requests *and* compiled to Z3. The two
backends are checked against each other **exhaustively** — the situation
space is finite (8,640 for the CMS), so `tests/test_engine.py` compares
every condition on every situation. Model↔code drift, the standing
problem of the spec-on-the-side examples, is closed by construction for
the ruled part of the system.

## What the human writes

Rules read like the tickets they come from, and each carries its
stakeholder sentence:

```yaml
- id: no_self_decision
  description: "Nobody may publish or reject an article they authored
    themselves — separation of duties, with no exception for admins."
  effect: deny
  when: 'action in ["publish", "reject"] and actor.is_author'
```

Semantics are Cedar/XACML-shaped and stated once: **deny overrides allow;
silence means deny.** Transitions are additionally guarded by the
lifecycle table (`publish` is only *defined* on `in_review`), so
permission rules and the state machine compose — and the analyzer reasons
about the combination.

There are no handlers to write. `POST /articles/7/publish` exists because
the lifecycle table says `publish: in_review → published`; it refuses with
`403 {"denied_by": "no_self_decision"}` because that rule says so. One
vocabulary from ticket → rule → solver finding → runtime error.

## What the gate catches (real output)

`rulesets/cms-buggy/` applies two locally-reasonable edits: LEG-77's
"unpublished material must not be accessible to anyone except the person
who wrote it" is added as `strict_privacy`, and `no_self_decision` is
dropped ("admins found it annoying"). Held to the **frozen** gate
(`--gate rulesets/cms`), the analyzer returns seven named findings:

```
FAIL DEAD allow rule 'editor_read_all': it never grants anything
     (overridden where it overlaps: deny_inactive, strict_privacy)
FAIL S2_separation_of_duties
     counterexample: {role: editor, action: publish, state: in_review,
                      active: true, is_author: true, has_title: true, has_body: true}
     allowed by: editor_decide
FAIL P2_review_by_non_author: IMPOSSIBLE — blocked by deny rule(s): strict_privacy
FAIL feat_publish_lifecycle: step 4 (ed read): expected allow, got deny (rule: strict_privacy)
FAIL feat_no_self_publish: step 3 (ed publish): expected deny, got allow (rule: editor_decide)
FAIL feat_boundaries_hold: step 2 (vera read): denied by strict_privacy, expected default_deny
FAIL feat_nightly_import: step 5 (imp-bot publish): denied by importer_scope, expected no_self_decision
VERDICT: FAIL (7 finding(s))
```

Every direction of this repo's gate doctrine appears at once:

- **safety** (S2): the *removed deny* is caught universally, with the
  concrete situation and the allow rule that now grants it;
- **possibility** (P2): the *added deny* is caught killing the editorial
  workflow — the classic safety-only blind spot ("the safest CMS serves
  nothing") — and the solver names the blocking rule;
- **dead rules**: `editor_read_all` still *looks* fine in the file, but Z3
  proves it never changes a decision anymore — the silent-masking bug that
  buried 1980s rule bases;
- **feature runs**: expected *denials by name* mean even a missing deny
  rule fails a scenario ("expected deny, got allow").

The same file replayed over real HTTP (`live_demo.py`) must reproduce the
same outcomes including `denied_by` names, plus a visibility probe: the
list endpoint as anonymous shows exactly the items the decision function
predicts.

A third direction, from developing this very example: an earlier draft
included `archived_locked` ("an archived article may not be modified by
anyone below admin") — reasonable, ticket-shaped, *and provably useless*:
the analyzer reports `DEAD deny rule 'archived_locked': it never refuses
anything that another rule would have allowed`, because default-deny
already covers every situation it names (safety S7 holds without it, over
all 3,600 situations). The solver doesn't just find bugs; it **shrinks the
rule base** — the opposite of how rule systems historically decayed.

## Extension episode: background processing (SYND-9, nightly imports)

The first realistic ticket after v1 — *"import nightly published articles
from a few publishers"* — is the classic seam where rule systems
historically lost ownership: background jobs get a database connection and
a cron entry, and the rules stop being the program. The design principle
here: **a background job is just another actor.** The importer is a plain
HTTP client (`importer.py`) with the `imp-bot` identity (role `importer`);
it gets no back door, so everything interesting about it is policy:

```yaml
- id: importer_scope
  description: "SYND-9: the import pipeline is contained — it may only
    create articles, submit them for review, and read; a compromised
    importer must not be able to edit, delete, or decide anything."
  effect: deny
  when: 'actor.role == "importer" and action not in ["create", "read", "submit"]'
```

What the ticket turned into (scoring falsifier RB1 from note 13):

- **Rule-base diff**: one role, one provenance field (`source`), three
  rules, one assumption edit — the whole domain change.
- **Gate ratchet** (a human spec ceremony, as required): S8 (imports carry
  provenance), S9 (pipeline containment — the blast radius of a stolen
  importer credential, checked over all situations), P6, one feature run,
  and one new gate kind (below).
- **Clients, not engine**: `mock_publishers.py` (three canned feeds) and
  `importer.py` (idempotent, dedups by `source`). `engine/` is untouched —
  **zero engine changes**; the analyzer grew two *generic* checks (~35
  lines) that the episode forced. `import_demo.py` runs two "nights"
  end-to-end: 7 imported, second run 0/7 skipped, imp-bot's tampering and
  self-publishing refused by name over HTTP, an editor publishes, the
  public reads. (`check.sh` step 8.)

`rulesets/cms-import-naive/` is the obvious first draft — syndicate
straight to published ("the publisher already reviewed it"), no
provenance, no containment, assumption forgotten. The frozen gate returns
five named findings:

```
FAIL role 'importer' can create items, but the assumptions say it can never be
     an author — stale assumption: symbolic analysis would silently skip every
     importer-authored situation
FAIL S8_imports_have_provenance    counterexample: {role: importer, action: create, ...}
FAIL S9_import_pipeline_contained  counterexample: {role: importer, action: syndicate, ...}
FAIL lifecycle: transition 'syndicate' (draft -> published) enters 'published',
     but the gate allows entry only via ['publish']
FAIL feat_nightly_import: step 1 (imp-bot create): expected deny, got allow
VERDICT: FAIL (5 finding(s))
```

Two of those findings are new *gate kinds* the episode exposed:

- **Stale assumptions are now detected.** Adding a role that can create
  falsifies `a_authors_are_staff` — and a stale assumption doesn't fail
  loudly, it silently *excludes* the importer-authored situations from
  every other symbolic check (features still pass, because the runtime
  ignores assumptions — exactly the unsound gap). The analyzer now
  cross-checks: every role the rules let create must be an assumable
  author. The README's "assumptions are trusted, not proven" limit is now
  partially closed, mechanically.
- **The lifecycle table is now gated.** S4 ("publish only from review")
  quantifies over the `publish` action — a *new* transition
  (`syndicate: draft → published`) sails past it and past every rule-level
  property. The gate gained structural jurisdiction:
  `lifecycle: only_into: {published: [publish]}`.

What stayed **outside** the rules, honestly: dedup ("no two articles with
the same source") is a cross-item invariant the per-situation vocabulary
cannot state — it lives in the importer client, and would properly belong
to a store constraint (the P9 invariant→Postgres-compiler direction); and
the nightly *schedule* is infrastructure (cron), not policy. RB1 score for
this ticket: domain change = rules + clients only; engine untouched; gate
*language* needed two generic extensions.

## Domain-transfer experiment: a receivables tracker (same engine)

How transferable is this across *adjacent but different* domains? Third
service, deliberately unlike a CMS: **tracking money you are owed**. Users
register claims (the amount, the approximate payer name *or* an exact
payment reference, and a due date); the bank emails transaction
notifications; the system keeps a dashboard and sends overdue reminders
(`rulesets/receivables/`, `./check.sh` stages 6, 9, 11).

The domain brings four things the CMS never had, and where each landed is
the transferability result:

**Landed as YAML** (290 lines: 13 rules, 10 safety, 7 possibility, 3 gated
lifecycle entries, 4 features):

- **Money truth**: only the bank feed settles — `only_feed_settles` denies
  *admins* too, and R3 ∀-verifies it (the demo shows the admin's settle
  attempt bouncing with a named 403).
- **Absolute tenancy**: users only ever touch their own claims (R2);
  the dashboard *is* the read rule — the live probe shows rita seeing
  exactly her claims and uma hers.
- **Append-only ledger**: paid/written-off claims are read-only for
  everyone (R5), nothing is ever deleted (R10).
- **The calendar as law**: `no_premature_overdue` denies `mark_overdue`
  unless `resource.is_past_due` — even for the clock bot itself. The
  sweeper is deliberately dumb (it attempts every awaiting claim) and the
  *rules* refuse the premature ones by name: the rules hold the clock
  accountable, not vice versa.
- The registration contract from the ticket is two deny rules:
  `claim_needs_terms` (amount + due date) and `claim_needs_identification`
  (payer name *or* reference).

**Forced generic engine growth** (~100 net lines, zero domain words —
the honest cost of the transfer):

- **Time.** The vocabulary had no clock. New: declared projections
  (`projections: [{name: is_past_due, kind: date_passed, field:
  due_date}]`) computed by the engine from its own date (`--today`; a
  `--mutable-clock` test seam lets demos and feature replays advance it
  deterministically). The analyzer treats projections as free booleans;
  the exhaustive backend test covers them.
- **Multi-source transitions.** `settle` must fire from `awaiting` *and*
  `overdue` (late payments still land — possibility W2 guards it);
  transitions are now keyed (action, source).
- **Feature clock.** Scenario files carry `clock: {today: …}` and
  `advance_days` steps, honored by both the pure and the HTTP executor —
  so "time cannot be rushed" is itself a frozen, replayable feature.

**Stayed client-side, correctly** (the projection boundary again): parsing
the bank emails, the *matching* itself (exact reference, else
case-insensitive payer name + exact amount — fuzzy and cross-item, beyond
any per-situation vocabulary), reminder dedup, and cron.

Two observations worth keeping:

- **Containment needed no deny rules this time.** The CMS importer needed
  `importer_scope` because `own_draft` granted it things (it authors
  articles). The receivables bots never own claims, so default-deny plus
  tight allows suffice — and the dead-rule check is what tells you which
  regime you're in: scope denies here would be *provably dead*.
- **RB2 signal:** the exhaustive runtime↔Z3 agreement check is now 26,880
  situations for this ruleset (~80s of the test suite). Exhaustive
  enumeration scales exponentially in projections; the per-condition
  projected-space or fully symbolic equivalence check is the known next
  step.

## Why this framing, and where it stops

The 1980s built whole businesses on rule engines (OPS5, CLIPS, Drools,
DMN) and the pattern survives today precisely where this example sits:
policy (Cedar, OPA), decisioning (DMN in insurance/banking), workflow.
Rule systems died where rule *interactions* became unauditable — thousands
of rules, no way to ask "does any rule ever...". That failure mode is
exactly what an SMT solver removes: every check above is a solved query
over the rule semantics, not a code review. Conversely, the formal-methods
framing's standing weakness — the spec and the code are two artifacts that
drift — disappears because there is only one artifact. The two framings
are not rivals; **rules are the programming surface, the solver is the
reviewer, and the one thing left to prove the hard way is the generic
engine, once** (this repo's note 12, pattern 1: Cedar is the
industrial-strength version — a Lean-verified engine under a small policy
DSL).

Honest limits, kept sharp on purpose:

- **The projection boundary.** The analyzer sees `actor.is_author` as a
  free boolean — a finite projection of a relational fact. Anything the
  projection can't say (at most 3 published articles per author; "editor
  who reviewed it") needs new vocabulary or is out of reach. Wrong or
  stale projections are the residual bug class: a demoted author still
  `is_author` — the stale-role race that `examples/cms/model` catches at
  rung 2 is *invisible* here. Single-state rules still can't see time.
- **Assumptions are trusted, not proven.** `a_authors_are_staff` is
  reviewable and load-bearing; if role demotion is ever added, it becomes
  false and the analysis silently optimistic. The authorship direction is
  now cross-checked mechanically (see the import episode), but that is one
  derived fact, not a general assumption-discharge story.
- **The engine is ~975 lines of unproven Python.** Fine for a research
  example; the production version of this pattern uses a *verified*
  engine (Cedar) so trust rests on one proof plus per-change analysis.
- **Rules don't compute.** Rendering, search, diffing, billing arithmetic
  need real code; migrations stay in P1/P3 territory. The claim is not
  "everything is rules" but "everything *domain-policy-shaped* is rules" —
  which for a CRUD SaaS is a large share of what tickets actually change.

## What a developer's day looks like

1. A ticket arrives in English. An LLM drafts the rule (a 5-line YAML
   diff, not a handler); you review it next to the sentence it translates.
2. `analyze` runs in CI: contradictions with the frozen gate, dead rules,
   killed workflows — named, with concrete situations, before merge.
3. The change deploys by *loading* — the engine didn't change, so there is
   nothing else to review.
4. An agent optimizing or extending the system edits `rules.yaml` freely;
   `safety.yaml` and `features.yaml` are frozen for it, mechanically
   (`--gate` points at the pinned copy — exactly the P4/P5 contract, at
   rule altitude).

## Map

| Path | What |
|------|------|
| `check.sh` | one-command entry: tests + 5 analyses + 5 live demos |
| `rulesets/cms/` | the CMS: rules + frozen gate (safety, features) |
| `rulesets/cms-buggy/` | two planted edits; must FAIL against the frozen gate |
| `rulesets/cms-import-naive/` | the obvious import extension; must FAIL (5 findings) |
| `rulesets/tickets/` | a different service on the same engine (generality proof) |
| `rulesets/receivables/` | third domain: money owed, due dates, bank feed (transfer test) |
| `engine/` | generic: conditions (two backends), rule base, store, HTTP server, clock |
| `analysis/analyze.py` | Z3 gate: dead rules, assumptions, ∀-safety, ∃-possibility, lifecycle, features |
| `live_demo.py` | replay the frozen features over real HTTP + visibility probe |
| `mock_publishers.py` | the external side: three canned publisher feeds |
| `importer.py` | the nightly job — an unprivileged HTTP client under the rules |
| `import_demo.py` | two "nights" end-to-end: import, dedup, containment, editorial finish |
| `mock_bank.py` | transaction notification emails, in daily batches |
| `receivables_bots.py` | feed matcher, overdue sweeper, reminder notifier |
| `receivables_demo.py` | the whole receivables story across two dates |
| `tests/` | unit tests incl. exhaustive runtime↔Z3 agreement |

Research discussion: `research/13-rule-based-cms.md`.
