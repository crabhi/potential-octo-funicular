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
