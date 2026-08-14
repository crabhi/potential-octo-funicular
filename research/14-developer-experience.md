# 14 · Developer experience: building a SaaS app end to end as rules

**Question.** Notes 12–13 established that rules-as-the-program is sound
and general. This note asks the question that decides adoption: **what
does developing this way actually feel like?** Method: build a complete
application — Flowdeck, a multi-tenant team kanban (`examples/taskboard/`)
— exactly as the method prescribes, with an unedited journal
(`examples/taskboard/DEVLOG.md`), and extract the experience honestly,
frictions first-class. The episode also forced the last "real app" gap
closed: a **web UI derived from the rule base** (`engine/ui.py`, generic).

## The shape of the work

The application is: 7 English tickets → 150 lines of rules.yaml → a frozen
gate (13 ∀-properties, 8 ∃-witnesses, 2 gated lifecycle entries, 5
scenarios) → `app.py` (boot + seed through the rules). **Zero lines of
app-specific handler or UI code.** Everything clickable — board columns,
cards, buttons, banners, the `/ui/rules` page — is derived from rules.yaml
by a generic module that also serves the CMS unchanged (screenshots in
`docs/slides/img/`, including the same UI on both apps).

Timeline, measured: tickets → green gate in about an hour of author time,
**4 analyzer rounds at ~0.18 s each**. Almost all of the hour was spent
*writing two YAML files*; effectively none of it debugging. Compare the
unit of iteration in ordinary development: write handler, wire route,
write tests, run, read stack traces. Here the unit is a sentence-shaped
stanza and a solver verdict.

## What the reviewer-solver caught (all real, none planted)

| Round | Finding | Class |
|---|---|---|
| 1 | `unknown variable 'actor.is_assignee'` | typo = load error, named |
| 1 | prediction "janitor_scope is dead" **falsified** — an unguarded allow made it load-bearing | solver knew the interaction; author didn't |
| 2 | S2: `{role: anonymous, action: start, assigned_to_me: true}` **allowed by assignee_moves** | real authz hole #1: assigning a task to "anonymous" hands work to the public |
| 2 | S5: `{role: admin, action: submit, assigned_to_me: false}` **allowed by admin_oversees** | real authz hole #2: the broad staff allow quietly granted the team's work |
| 2 | two feature probes got the *wrong deny name* | overlapping denies are order-named |
| 3 | `DEAD deny rule 'janitor_scope'` — after the round-2 fix | the solver shrank the rule base; S11 proves containment instead |

Round 4: PASS. The round-2 draft is preserved (`rulesets/taskboard-round2/`)
and `check.sh` holds it to the frozen gate forever — development history as
a permanent regression.

Nobody writes the test where the task is assigned to the anonymous user.
The ∀-check considers that situation because it considers *all* 34,560; it
then hands you the granting rule by name. Both real holes were
**interaction** bugs — each rule read fine alone.

## How it feels (the honest phenomenology)

1. **Review latency is gone.** 0.18 s from edit to verdict, and the
   verdict is *terminal*: PASS means mergeable, FAIL names the situation
   and the rule. The loop feels like a type checker for authorization —
   with the crucial difference that it also demands liveness (∃-witnesses)
   so "deny everything" cannot pass.
2. **The gate is where the thinking happens.** Writing `safety.yaml`
   forced questions the rules let me fudge ("may staff work a task?").
   ∀-properties are the design review; the rules are just the design.
3. **One vocabulary carries end to end, visibly.** The TB-4 sentence
   appears in the ticket, the rule description, the solver counterexample,
   the greyed button's tooltip, and the 403 banner the user sees. When
   mira clicks *approve* on her own task, the banner says `refused by rule
   no_self_approval` — the exact string the analyzer reasons about.
4. **Predictions get falsified fast.** I predicted the containment deny
   was dead (receivables precedent); the solver showed it load-bearing,
   then dead one fix later. The dead-rule check turns out to be a *live
   diagnostic of the containment regime* — worth knowing before deleting
   any deny.
5. **The app is a byproduct.** After the gate went green, "building the
   app" was: write a seed list. The UI existed already, for every rule
   base at once.

## Frictions found (kept sharp — these are the research)

- **Namespace surprise.** Relational projections read like actor facts but
  live under `resource.*` (`resource.assigned_to_me`). Caught at load, but
  the naming needed a convention. Cost: one round.
- **Deny-order naming.** `denied_by` is declaration-order among matching
  denies; named-denial probes must sit in the minimal state that triggers
  them. A future analyzer check could flag ambiguous probes.
- **Edit is blind to proposed values.** Rules see an edit's *current*
  fields, not the incoming ones — "a title can never be emptied later" is
  not expressible; S3 guards creation only. Vocabulary gaps fail loud;
  *semantic* gaps like this fail silent. Sharpest edge found. (Engine fix
  is known: evaluate edit against proposed values too.)
- **Assumption unsoundness is still real.** Nothing stops `assignee:
  "ada"` at runtime; an `a_assignees_are_team` assumption would be
  trusted, not proven (note 13's standing limit — only authorship is
  cross-checked mechanically today).
- **The vocabulary is a budget you manage by hand.** Without `has_`
  opt-out the space is 276,480 situations; with it, 34,560 (exhaustive
  backend agreement: ~85 s of `check.sh`, RB2's known scaling edge).
- **The engine wants to be a package.** Flowdeck path-shims
  `../rule-driven-cms`; fine for research, grating for product work.

## Transfer-cost trend (falsifier RB1, third data point)

- CMS → tickets: **0** engine lines.
- CMS → receivables: ~100 generic lines — the missing concept was *time*.
- → Flowdeck: ~60 generic lines — the missing concept was *actor↔resource
  relations* (tenancy, assignment) — plus the generic UI (~370 lines) that
  every rule base gains simultaneously.

Each new domain has cost exactly **one missing generic concept**, and the
per-domain YAML stays flat (~150 lines). Prediction for RB1: a fifth
domain (e.g. approvals/expenses) costs **zero** engine lines — time +
relations + validation cover it.

## Falsifiers for this note

- **DX1**: an experienced web developer, given TICKETS.md and one worked
  example, ships a comparable ruled app in under a day without touching
  the engine. (Falsified if the projection/namespace model needs engine
  reading to use.)
- **DX2**: the same seven tickets implemented conventionally (handlers +
  tests) by a strong LLM contain at least one of the two interaction holes
  the gate caught here. (Falsified if conventional codegen avoids both.)
- **DX3**: the edit-proposed-values gap causes a real missed bug in a
  future episode before the engine closes it. (Standing risk, tracked.)

## Verdict

For the policy-shaped core of a SaaS app, the developer experience is
*better than conventional development on its own terms*: faster loop,
terminal verdicts, bugs caught that tests would miss, and the UI/API for
free. The costs are real but specific and enumerable: naming conventions,
probe placement, the edit blind spot, trusted assumptions, and the
exhaustive-check budget. None of them is a wall; all of them are now
written down where the next episode can test them.
