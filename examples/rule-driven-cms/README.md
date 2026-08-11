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
 rulesets/cms/rules.yaml     the CMS: roles, lifecycle, 11 allow/deny rules   105 lines
 rulesets/cms/safety.yaml    FROZEN gate: 7 ∀-properties, 5 ∃-properties       68 lines
 rulesets/cms/features.yaml  FROZEN gate: 4 end-to-end scenarios               68 lines
 ──────────────────────────────────────────────────────────────────────────────
 engine/ + analysis/         generic, domain-free, reusable                  ~975 lines
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
space is finite (3,600 for the CMS), so `tests/test_engine.py` compares
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
(`--gate rulesets/cms`), the analyzer returns six named findings:

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
VERDICT: FAIL (6 finding(s))
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
  false and the analysis silently optimistic. (The fix is mechanical —
  re-derive assumptions from the rules that establish them — but not
  built.)
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
| `check.sh` | one-command entry: tests + 3 analyses + 2 live services |
| `rulesets/cms/` | the CMS: rules + frozen gate (safety, features) |
| `rulesets/cms-buggy/` | two planted edits; must FAIL against the frozen gate |
| `rulesets/tickets/` | a different service on the same engine (generality proof) |
| `engine/` | generic: conditions (two backends), rule base, store, HTTP server |
| `analysis/analyze.py` | Z3 gate: dead rules, ∀-safety, ∃-possibility, lifecycle, features |
| `live_demo.py` | replay the frozen features over real HTTP + visibility probe |
| `tests/` | unit tests incl. exhaustive runtime↔Z3 agreement |

Research discussion: `research/13-rule-based-cms.md`.
