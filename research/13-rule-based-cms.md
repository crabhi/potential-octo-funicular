# Rule-based systems as the programming surface: a whole service, ground up

**Date, status:** 2026-08-11, draft (built alongside
`examples/rule-driven-cms/` — every claim about the example is executable
via its `check.sh`).

**The developer's question:** every artifact so far models one facet of a
system with a deliberately small model. What does the workflow look like
when a human builds a **full web service (CMS) from the ground up** — and
is "formal methods" even the right framing for that, versus **rule-based
systems**?

## TL;DR / verdict

The framings are not rivals; they differ in **where the primary artifact
lives**, and the right synthesis for a ground-up SaaS is:

> **Rules are the program** (executable, one artifact, no spec↔code gap
> for the domain), **the solver is the reviewer** (the queries rule-based
> systems always needed and never had), and **proof effort concentrates on
> the one generic engine** (prove once — note 12's pattern 1, i.e. the
> Cedar shape).

Under the formal-methods framing, the code is primary and the spec holds
it to account from outside; the permanent tax is the model↔code boundary
(P3's harness, track C's MBT, trace validation — half this repo exists to
police that boundary). Under the rule-based framing there is **no boundary
for the ruled part**: the artifact the human reviews is the artifact the
server executes. The boundary doesn't vanish — it moves into the generic
engine (small, domain-free, provable once) and into the **projections**
(the finite vocabulary the rules see: `actor.is_author`, `resource.state`,
`has_title`). That relocation is the whole trade, and it is a good trade
for exactly the workloads this project targets: CRUD + authz + workflow,
where most tickets change *policy*, not *computation*.

## Why rule-based systems failed the first time, and what changed

The 1980s–90s built real businesses on production systems (OPS5, CLIPS,
ART) and their descendants still run claims processing and credit
decisioning (Drools, IBM ODM, DMN — decision tables are the surviving UX).
The two failure modes were:

1. **Interaction opacity.** At 10³–10⁴ rules nobody could answer "does any
   rule ever let X happen?" or "does this new rule silently disable an old
   one?" — the maintenance cliff that ended most expert systems (the
   knowledge-acquisition bottleneck was about *validating* knowledge, not
   collecting it).
2. **The rules didn't own the system.** The engine sat beside ordinary
   code; the interesting failures happened at the seam.

(1) is precisely an SMT workload. The example's analyzer answers, per rule
change, in ~2s: *is any rule dead* (never changes a decision), *does a
∀-safety property hold over all situations*, *does a workflow still exist*
(∃-witness), *is every lifecycle state reachable* — each finding named,
with a concrete situation. Industry converged on the same move from the
policy side: Cedar ships a Lean-verified engine **plus a
proven-complete symbolic analysis** (SymCC over policies), Zelkova does it
for IAM, Margrave did it for XACML in 2010. What the example adds over
those: the rule base covers the **whole service** (lifecycle, validation,
visibility — not just authz), and the gate is bidirectional (safety AND
possibility AND frozen feature runs), per this repo's guardrail 2.

(2) is answered by construction: the engine is generic (zero domain words
outside docstrings; a second service — tickets — runs on it unchanged), so
the seam between rules and code is a single, stable, provable interface
rather than one seam per feature.

## What the example demonstrates (all executable)

- **~240 lines of YAML are the CMS**; ~975 lines of Python are the
  domain-free engine + analyzer, amortized over every future service
  (demonstrated: `rulesets/tickets/`).
- **One condition grammar, two backends** (runtime eval + Z3), agreement
  checked **exhaustively** over the finite situation space (3,600
  situations) — the translate/validate split (guardrail 5) collapses to a
  mechanically-closed loop.
- **The frozen-gate contract survives the reframing** (guardrail 1): two
  plausible edits (a legal-privacy deny added, separation-of-duties deny
  removed) produce six named findings against the pinned gate — including
  the two classic blind spots: a deny that kills a feature (caught by
  ∃-possibility + feature runs, not by any safety property) and a removed
  deny (caught by ∀-safety + an *expected-denial-by-name* feature step).
- **Dead-rule detection reverses rule rot**: the analyzer proved a
  reasonable-sounding guard (`archived_locked`) redundant during
  development and it was deleted — the solver shrinking the rule base is
  new relative to how these systems historically only grew.
- **One vocabulary end to end** (guardrail 6): ticket sentence → rule id →
  solver finding → `403 {"denied_by": rule_id}` over real HTTP.

## Where the framing stops (kept deliberately sharp)

- **Projections are the new trust root.** `actor.is_author` is a boolean
  shadow of a relational fact. Cross-item invariants ("≤3 published per
  author"), arithmetic, and anything relational need vocabulary the
  situation abstraction lacks; EPR/mypyvy (note 10) is the escalation
  path if we ever need quantified projections.
- **No time.** Single-situation rules cannot see the stale-role/TOCTOU
  races that `examples/cms/model` catches with Quint. The assurance ladder
  keeps its rungs: rules (this note) < temporal models < parameterized
  proofs. A demoted author still `is_author` here.
- **Assumptions are axioms.** `a_authors_are_staff` is reviewable but
  unproven; adding role demotion would falsify it silently. Deriving
  assumptions from the rules that establish them is mechanical and unbuilt.
- **Rules don't compute.** Billing arithmetic, rendering, search, and
  migrations (P1/P3) remain code — the claim is that *domain policy* is
  rules, and for a CRUD SaaS that is where most ticket-driven change lands.
- **Engine trust.** Ours is unproven Python; the production form of the
  pattern is a verified engine (Cedar's Lean proofs) or our own track-D
  Dafny→Go shape under this DSL.

## Falsifiers / predictions

- **RB1 (expressiveness).** Within the next ~20 realistic CMS tickets,
  ≥80% are expressible as rule/lifecycle/gate diffs with no engine change.
  Falsified if routine tickets keep forcing engine edits — then the
  "generic engine" claim is cosmetic.
- **RB2 (scale).** At ~100 rules, per-change analysis stays <10s and dead-
  rule findings stay interpretable (the finding names ≤3 masking rules).
  Falsified by solver blowup or unreadable findings — then we've rebuilt
  the 1980s cliff with extra steps.
- **RB3 (LLM fidelity).** Ticket→rule translation with the analyzer in the
  loop needs fewer human corrections than ticket→handler-code with tests,
  on the same tickets (the note-06 translate/validate bet, now at rule
  altitude; measurable in a P4-style episode).
- **RB4 (the projection gap bites).** A temporal twin of the rule base
  (Quint, rung 2) finds at least one real race the rule analysis certifies
  as safe — predicted: the demoted-author window. If it finds none, rung 2
  is overpriced for rule-driven services.
- **RB5 (gate strength transfers).** An agent asked to "fix" the buggy
  ruleset under the frozen gate converges in ≤2 rounds without weakening
  possibility (the P4 episode-2 result, expected to replicate cheaper
  because diffs are declarative).

## Episode: the first extension ticket (SYND-9, 2026-08-11) — RB1 evidence

The first post-v1 ticket — *nightly import of published articles from a
few publishers* — is background processing, historically the seam where
rule systems lose ownership of the system. Design decision: **a background
job is just another actor** — the importer is an unprivileged HTTP client
(`imp-bot`, role `importer`); scheduling is cron; no back door exists to
lose.

Scoring against RB1 ("realistic tickets land as rule diffs, no engine
changes"):

- **Domain change**: 1 role + 1 provenance field + 3 rules + 1 assumption
  edit, plus two clients (mock feeds, importer). `engine/` untouched —
  RB1 holds for the engine.
- **Gate change** (human ceremony, gate ratchets): S8 provenance, S9
  pipeline containment (the stolen-credential blast radius, ∀-checked),
  P6, one feature run — *and two new gate kinds the episode forced*:
  1. **Stale-assumption detection.** Adding a creating role falsified
     `a_authors_are_staff`; the failure mode is silent unsoundness (the
     solver excludes importer-authored situations; runtime features still
     pass because assumptions are analyzer-only). New generic check: every
     role the rules let create must be an assumable author. This partially
     closes the "assumptions are axioms" limit — one derived fact, not a
     discharge story.
  2. **Lifecycle-table jurisdiction.** The naive design (`syndicate:
     draft → published`, "the publisher already reviewed it") evades S4,
     which quantifies over the `publish` *action*. New gate section
     `lifecycle: only_into: {published: [publish]}` gives the frozen gate
     structural authority over the third artifact. Rule-level ∀-properties
     do not cover lifecycle edits — worth remembering for RB2.
- **Refused by the framing, correctly**: dedup/idempotency is a cross-item
  invariant the situation vocabulary cannot state (lives in the client;
  properly a store constraint — the P9 direction), and the schedule is
  infrastructure. The projection boundary is real and bit on ticket #1.

Naive variant kept as `rulesets/cms-import-naive/`: 5 named findings
against the frozen gate. RB1 verdict so far: **holds, with a caveat** —
the *rule base* absorbed the ticket, but the *gate language* needed two
generic extensions (~35 lines of analyzer). Prediction for RB1 scoring:
gate-language growth should flatten (new tickets reuse `only_into` and the
authorship check); if every ticket keeps demanding new gate kinds, the
framing is leaking complexity into the analyzer instead of removing it.

## Episode: domain transfer (receivables, 2026-08-11)

The developer's question: how transferable is the approach across
adjacent-but-different domains? Test: replace the domain entirely — a
tracker for money you are owed (users register amount + approximate payer
name or exact reference + due date; bank transaction emails settle claims;
dashboard; overdue reminder emails). `rulesets/receivables/` +
`receivables_demo.py`, same engine.

**Result: the transfer works, and its cost is measurable.** Three-way
split of where the new domain landed:

1. **Pure YAML (290 lines)** — everything the domain *means*: money truth
   (only the bank feed settles; admins bounce off `only_feed_settles`),
   absolute tenant isolation, an append-only ledger, well-formedness of
   claims, and the calendar as law (`no_premature_overdue` refuses even
   the clock bot). All ∀-checked; 13 rules, all effectual; four frozen
   features incl. a temporal one that replays over live HTTP.
2. **Generic engine growth (~100 net lines, zero domain words)** — the
   honest transfer cost, and it is *conceptual, not volumetric*: the
   engine lacked **time**. Declared projections (`date_passed` →
   `resource.is_past_due`) + an engine clock (`--today`, `/__clock` test
   seam), multi-source transitions (`settle` from awaiting *and* overdue
   — late payments must land, possibility W2), and a feature-file clock
   (`advance_days` in both executors). Each is now vocabulary every future
   domain gets for free — the same flattening-curve prediction as the
   import episode, one data point stronger.
3. **Client-side, correctly refused by the vocabulary** — email parsing,
   the matching itself (exact reference, else normalized payer name +
   exact amount: fuzzy AND cross-item), reminder dedup, cron. Consistent
   with the projection boundary; a production system would want the
   matcher's decisions auditable (it prints match evidence) and eventually
   store-level constraints (P9).

Cross-episode contrast worth keeping: **bot containment needed deny rules
in the CMS but not here.** The importer authors articles, so `own_draft`
granted it things a deny had to take back (`importer_scope`); the
receivables bots never own claims, so default-deny + tight allows suffice
— scope denies here would be *provably dead*, and the dead-rule check is
what distinguishes the two regimes. "Which containment style do I need"
is a solver query, not a style guide.

New falsifier-relevant observations:

- **RB2 now has a concrete number**: exhaustive runtime↔Z3 agreement is
  26,880 situations for receivables (~80s in CI). Exponential in
  projections; next step when it hurts: per-condition projected
  enumeration (a condition's truth depends only on the variables it
  mentions) or a fully symbolic equivalence check.
- **RB6 (new): the clock is a trust root.** `is_past_due` is only as true
  as the engine's date. The analyzer verifies "overdue only when past
  due" *relative to the projection*; a skewed server clock breaks it
  silently. Prediction: the temporal twin (RB4) should also model clock
  skew between the sweeper's view and the engine's.
- Multi-entity domains remain the open structural limit: receivables
  dodged it (transactions live in the bank's world; only claims are
  ruled), but invoice↔payment↔dunning as *linked ruled entities* would
  need N rule bases + client joins, or engine work on relations.

## Relation to the rest of the repo

This is note 12's pattern 1 (verified engine + DSL surface) built
end-to-end and widened from authz to the whole service; `examples/cms`
remains the formal-methods-framing twin of the same domain — the two
directories are now a controlled comparison of the framings. The
escalation ladder is unchanged; what changes is the *default rung for new
work*: start by asking "is this ticket a rule diff?", and only climb when
the answer is no (time, relations, computation).
