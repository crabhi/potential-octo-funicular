# Note 15 — The verified boundary is a kernel API; the UI layer is free

**Status:** prototype shipped (`examples/helpdesk/` — Relay), guardrail 10
recorded. Follows note 13 (rules are the program) and note 14 (DX study).

## The redirect

Note 14's answer to "where does the UI come from?" was a generic UI
derived from the rule base. The developer rejected that as the product
surface (2026-08-14): **UX customizability is crucial** — the implementing
agent must be free in the UI, while the interaction logic stays guarded by
the rules. The requested shape: hand-written htmx UI over a verified
boundary at the class/function level.

This is a better factoring, and it is worth stating why in architecture
terms rather than taste terms:

* A generated UI couples the product surface to the rule vocabulary. The
  rule base knows lifecycle states and fields; it does not know that a
  support desk wants an "SLA breached" queue spanning three states, a
  brand, or an "Assign to me" button. Product surfaces are made of exactly
  such things.
* Deriving the UI from the rules also *smuggles reflection into the
  trust story*: it looks like the UI is "correct by construction", but the
  UI was never the thing that needed to be correct. Enforcement was.
* Putting the boundary at a function-level API makes the trusted computing
  base explicit and small: `kernel.visible / get / create / act / edit /
  delete`, plus pure `decide / affordances` for rendering. Everything
  above it is provably (by lint) incapable of touching state, hence
  *free* — an agent can redesign it all day and no review needs to ask
  "did policy change?"

## What was built

```
FREE      app.py (htmx, ~500 lines, zero policy)      ← agent-authored, restyle at will
BOUNDARY  engine/kernel.py (~200 lines, domain-free)  ← every call decided by the rules
          analysis/boundary.py (lint: app imports engine.kernel ONLY)
ANALYZED  rulesets/helpdesk (14 rules ← 7 tickets)    ← Z3 gate, frozen
```

* **Kernel** (`engine/kernel.py`): the only path to state. Reads decided
  (`visible()` *is* the read rule; `get()` raises `Denied` naming the
  rule), mutations decided-then-stored, `Decision` values for affordances.
  The JSON API and the old generic UI were refactored into adapters over
  the same kernel — one enforcement path, three surfaces. The generic UI
  is repositioned as *scaffolding* (rule-base diagnostics), per
  guardrail 10.
* **Two-phase edits.** The kernel decides an edit twice: may this actor
  edit this row, and may the row *become* the proposed value. This closed
  note 14's sharpest silent gap (tenant escape by editing the org/team
  field) for every service on the engine at once; the pure feature
  executor got the same semantics, so the exhaustive model↔code agreement
  still holds. All pre-existing gates replayed green.
* **Boundary lint** (`analysis/boundary.py`): app code may import
  `engine.kernel` and nothing beneath it — no `engine.store`, no
  `sqlite3`, no reach-around attributes, no mangled internals. Relay's
  check.sh requires the lint to PASS on `app.py` **and to FAIL on a
  preserved `bypass_variant/`** (a plausible three-line "close stale cases
  directly in SQL" shortcut). Honest scope: a lint plus name mangling is
  not a proof; the by-construction version is a process boundary or a
  language with visibility (guardrail 8). What it guarantees is that the
  bypass cannot happen *quietly*.
* **Relay** (`examples/helpdesk/`): third full domain on the engine —
  org tenancy, assignment, SLA escalation, sealed records, contained mail
  robot. 7 tickets → 14 rules; frozen gate 13 ∀ + 9 ∃ + 2 gated lifecycle
  entries + 42 feature steps; 19,200 situations exhaustively
  backend-agreed; round-1 analyzer PASS (~0.2 s) with both pre-registered
  predictions held (see the DEVLOG).

## Findings

1. **The freedom is real and it is cheap to prove.** The forged-request
   tests POST actions the UI never rendered (the robot triaging, a
   non-assignee resolving, a customer re-tenanting her case): all come
   back 403 naming the rule, with nothing written. "The UI is a client,
   not a guard" stops being a slogan and becomes a test suite. The UX
   layer produced real product affordances no reflected UI could invent —
   a cross-state SLA queue with per-persona counts, org-prefilled forms,
   locked-action disclosures — and none of it was reviewable for policy
   because none of it *could* carry policy.
2. **Affordances are the API that makes honest UIs cheap.** One pure
   `affordances(actor, row)` call powers allowed-buttons, locked-lists
   with rule names, and the edit form's availability. The generic UI and
   Relay render opposite affordance philosophies (grey-out vs. disclosure)
   from the same call — presentation choices, not policy forks.
3. **Containment without deny rules transferred as method knowledge.**
   Relay's five containments (nothing deleted, staff never reopen, only
   leads close, customers never touch staff states, robot scope) have no
   deny rules at all — tight allows + default-deny, proven by
   S-properties. Predicted before the first analyzer run; held. The cost
   surfaced honestly: those refusals now read `default_deny` instead of a
   stakeholder sentence — the *error-message vocabulary* is poorer where
   the rule base is leaner. Open idea: refusals could cite the nearest
   allow and why it did not fire ("mailbot_files grants open, reply — not
   triage"); solver-computable.
4. **The engine's domain vocabulary growth for domain #4 was zero lines**,
   confirming note 14's transfer-cost trend (time ~100 → relations ~60 →
   0). What did grow — kernel and lint — is architecture the developer
   asked for, domain-free and now amortized across all four services.
5. **Free-layer bugs stayed free.** htmx silently refuses to swap 4xx
   responses; the kernel's honest 403 toast didn't render until a
   one-listener opt-in. Caught by a screenshot, not a gate — and that is
   the correct outcome: nothing was at stake but pixels. The asymmetry
   (plumbing hours in the free layer, zero policy exposure) is the
   architecture working.

## Falsifiers / next probes

* **KB1 — the lint is too weak in practice.** Have a red-team agent write
  an app that passes `analysis.boundary` yet mutates state around a
  decision. `getattr`/`importlib` tricks are the obvious route; if a
  *plausible-looking* (not adversarial) bypass slips through, the lint
  needs AST-level call analysis or the boundary needs a process split.
* **KB2 — the kernel API is too small for real products.** Build a UI
  needing aggregation (counts by assignee), search, or pagination and see
  whether pressure to "just open the DB read-only" appears. A read-only
  reporting seam that still applies the read rule per row would be the
  test of whether reads-as-decisions scales.
* **KB3 — two-phase edits are not enough.** Concurrent writers between
  decide and write are unhandled (single-connection SQLite hides this).
  The P3 harness pattern (real Postgres, concurrent load) applied to the
  kernel would either find the anomaly or show the transaction wrapper
  that prevents it.
* **KB4 — default_deny UX.** Implement nearest-allow refusal explanations
  and check they do not leak information across tenants (an explanation
  is a disclosure channel — org walls apply to error messages too).

## Verdict

The developer's redirect resolves note 14's biggest open tension (generic
UI ↔ product UX) without giving back any guarantee: policy stayed in the
analyzed rule base, enforcement moved to a smaller and more explicit
boundary, and the UI became ordinary product code an agent may own
outright. For an LLM-built SaaS this is the shape to keep: **rules →
kernel → free surfaces**, with the boundary held by a named CI failure.
