# DEVLOG — Relay on boxes

The honest journal of building Relay as reviewed contracts + generated
bodies. Dates are session-local (2026-10-03).

## Setup decisions (asked of the developer)

- Domain: re-implement **Relay** (`../helpdesk/`) so the approach compares
  head-to-head with the rule-engine version.
- Guards (who may do what): **reviewed code** — plain Python predicates in
  `machine.py`, not black boxes.
- Holding a box to its description: **types + descriptions + tests**, with
  human-reviewed tests (`tests/reviewed/`) split from generated tests
  (`tests/generated/`).
- DSL: plain Python decorators and/or conventions (developer, mid-session).
- "Who plays the LLM?" — the developer could not decide and asked for an
  explanation (see README "Who plays the LLM?"). Default taken: no
  generator tooling in the framework; any agent works from
  `python -m boxkit brief`. For this build: sub-agents (a cheaper model)
  that may read **only their brief**.

## Monty, probed before building (pydantic-monty 1.0.0)

- Host dataclasses cross in as read-only views (`ClassInstance`); sandbox
  attribute writes stay in the sandbox; returning a wrapped object hands
  the host the original back.
- `ClassType(init=True)` lets sandbox code construct **real host
  dataclasses** — results arrive as genuine reviewed types. Dataclasses do
  not validate their fields, so boxkit conformance-checks every result.
- Methods of a host object are callable only if allow-listed; return
  values are NOT auto-wrapped (boxkit wraps recursively).
- `type_check_stubs` + `type_check=True` runs ty inside the worker.
  Gotcha found by the framework's own first test: **names starting with
  `_` in stubs are not visible** to the checked module (the contract
  protocol was first called `_BoxContract`; renamed `BoxkitContract`).
- Missing stdlib: `html`, `enum`, `string`, `textwrap`, `urllib`,
  `dataclasses.replace`. Escaping therefore arrives as a reviewed
  capability (`esc`) — which also makes "did the page escape?" a property
  a reviewed test can pin, not a library the body may or may not import.
- Per call: ~2 ms (checkout + feed + call); type check ~50 ms.

## Round 1 — logic boxes (route, sort_into_queues, intake_email)

Reviewed tests were written BEFORE any body existed (guardrail 3: gate
strength first). Three sub-agents, one per box, brief only.

| box | agent iterations | reviewed tests | note |
|-----|------------------|----------------|------|
| sort_into_queues | 1 | pass | flagged "partition" vs the cross-state breached queue, and that "before today" was read as strict `<` |
| intake_email | 2 (forgot `import re`) | **FAIL** | flagged: does the trim/drop-empty rule apply to replies? It assumed not |
| route | 1 | **FAIL** | flagged: non-numeric id in a PATH — Invalid or NotFound? It chose Invalid |

Both failures sat **exactly on the sentences the implementers reported as
ambiguous**. Each agent's ambiguity report predicted its own reviewed-test
failure. The ambiguity reports are worth as much as the code: they are a
review checklist for the description, written by the only reader that
takes the description literally.

Fix: tighten the two descriptions (contract change → `approve` → spec
hashes move). `boxkit check` then marked **exactly those two bodies
STALE** — `sort_into_queues` and the five UI boxes, whose stubs do not
include the edited text, kept their hashes. Round 2 sent each agent the
STALE line + the failing counterexample; both regenerated in one
iteration; reviewed tests pass.

Open description-review items (not fixed — for the human reviewer):
`sort_into_queues` says "Partition" although the breached queue overlaps
the state queues; the bounce wording of `intake_email` is unspecified
(tests do not pin it — deliberately).

## Round 1 — the UI family (document, sidebar, queue_page, case_page, new_case_page)

One implementer for all five, because they share an implicit vocabulary
no box type expresses: CSS class names (`document` owns the stylesheet;
the pages use the classes). Generating them separately would have needed
that vocabulary in the reviewed contract. Brief-only, as before.

- 3 gate iterations (forgot `from datetime import date` / `import json`
  — ty inside Monty named both), 2 render runs. **All 44 reviewed tests
  passed in round 1**, including hostile text on every page × 5 personas
  and "every rendered link/form is a route the router knows" (a property
  between two independently generated boxes).
- 22 ambiguity notes (persona-switch target, "Assign to me" scope,
  tombstone wording, notice headings…). None contradicted a reviewed
  test; all are presentation freedom the description deliberately leaves
  open. One self-imposed caution worth noting: it omitted the filename of
  removed attachments "as a precaution" — stricter than the description.
- Checked in a real browser (Playwright): persona switch via htmx sets
  the cookie and re-renders without nesting; pressing a locked "resolve"
  as quinn swaps in the named refusal (`only_assignee_resolves`, HD-4).
  Screenshots: `docs/slides/img/boxes-*.png` (`python screenshots.py`).

## The mutation run (guardrail 2, found by machine)

Deleting each of the 29 guard rules in turn: **24/29 killed** by the
reviewed policy grid. The five survivors were all ALLOW rules no witness
exercised (customer_follows, customer_edits, staff_attach, lead_removes,
mailbot_attaches) — a reviewed suite that would let an agent quietly take
features away. Added witnesses P17–P21 → **29/29 killed**; `mutants.py`
is now stage 5 of `check.sh`. (The rule-engine Relay's gate adds
features.yaml step runs on top of its ∃-witnesses; whether those cover
the same five rules was not checked here.)

## Review burden (honest)

Reviewed: model 115 + machine 544 + boxes 351 + shell 321 = 1,331 lines,
plus 566 lines of reviewed tests. Generated: 910 lines (8 boxes). The
rule-engine Relay: 278 lines of rules + 443 of gate YAML reviewed per app,
764 lines of free UI, and an engine reviewed once for all apps.

## Generated tests

One sub-agent, briefs only (no impl/, no reviewed tests), wrote 300
tests in `tests/generated/` (route 107, intake_email 56, queues 14, pages
123 + a small HTML/FakeDesk helper). All green against the bodies; it
found no implementation bug, and corrected one over-read of its own
(exact queue-cell text). Swapping in the preserved unescaped `case_page`
fails 27 of them, including an escape-specific one — so the generated
suite independently re-derives the XSS property the reviewed suite pins.
Caveat it flagged itself: some tests pin markup beyond the literal
description (persona option values, `<details>` for locked actions, six
`<th>` in order). Generated tests are free to over-pin — but then a
faithful regeneration of a box can fail them. Policy taken: when a box is
regenerated, its generated tests are regenerated with it; only reviewed
tests are fixed points.

## Full run

`./check.sh` from a fresh venv: 72 s, ALL CHECKS PASSED — 10 framework,
gate PASS, 44 reviewed + 300 generated tests, 5/5 bad variants caught at
their named stage, 29/29 rule-deletion mutants killed, boot + seed (9
cases, two via the mail robot).

## Revision — no review lock; business-area modules; src/test mirror (developer)

Three developer directives, applied in order:

1. **"Simplify. Get rid of the review lock."** The PR diff is the review
   surface: whoever reviews sees which reviewed files changed. Removed
   `REVIEW.lock`, `REVIEW.md` and `boxkit approve/status/digest`; the lock
   gate stage is gone. The preserved "unapproved kernel edit" variant lost
   its meaning and was replaced by one that still bites: reviewed code
   importing generated code (boundary lint). The per-box spec hash stays —
   it is not a review lock but how a body knows its contract moved.
2. **"Group generated code in a separate folder"**, made user-friendly in
   PRs: `.gitattributes` marks the generated folders `linguist-generated`,
   so GitHub collapses them; check.sh verifies the attribute.
3. **"Construct modules by business logic"; "generated under src and test;
   match module names"** (`relay.cases.model` ↔ `generated.relay.cases.model`).
   The flat model/machine/boxes/shell split (grouped by kind of code) became
   `people`, `policy`, `kernel`, `cases/`, `thread/`, `mail/`, `web/` — each
   business area holds its model, lifecycle, rules, contracts and effects.
   A uv project now (`uv_build`, `module-name = ["relay", "generated",
   "boxkit"]` — verified that one wheel ships all three; hatchling's
   `force-include` was the alternative before generated moved under src/).

Mechanics worth recording:
- Reviewed definitions were moved **verbatim** (extracted by AST, not
  retyped), and rules kept their per-entity registration order (deny
  order names the refusal).
- The spec hash was redefined over the TEXT of the closure types +
  signature + description, not the stub file (whose import lines and
  ordering depend on where things live). Verified: the new-formula hashes
  computed on the pre-move code equal those on the post-move code for all
  8 boxes — so the move provably changed no contract, and the bodies were
  re-stamped, not regenerated. Future moves no longer stale anything.
- Five per-box body files became five per-module mirrors; the three case
  pages had byte-identical `_toast` helpers (independently written per
  box) — merged once. Grouping by module gives generated code a natural
  place for shared helpers.
- Stubs are now dependency-ordered (a type alias after the classes it
  names), needed once types come from several modules.
- Generated tests were moved by a mechanical import rewrite (their helper
  module inlined, since `test/generated` must not shadow the `generated`
  package); reviewed tests were split by business area with shared
  fixtures in `test/relay/conftest.py`.

Result: check.sh green — 10 framework + 44 reviewed + 300 generated tests,
5/5 variants caught, 29/29 mutants killed, boot. Reviewed: 1,457 lines
(people 20, policy 75, kernel 330, cases 250, thread 153, mail 119, web
495) + 642 test lines; generated: 876 + 1,753 test lines.
