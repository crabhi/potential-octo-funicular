# Relay — a helpdesk with a FREE UI over a verified kernel

The guardrail-10 prototype: **the rules guard the interaction logic at a
class/function-level API; the UI on top is hand-written htmx and answers
to nobody.** UX customizability is a first-class requirement — so the
product surface is not generated from the rules; it is authored, styled
and reshaped freely, and it *cannot* weaken policy.

```
             ┌───────────────────────────────────────────────┐
   FREE      │  app.py — hand-written htmx UI (~500 lines)   │  redesign at will;
             │  queues · toasts · badges · forms · swaps     │  no policy here
             └───────────────────┬───────────────────────────┘
                     from engine import kernel   ← the ONLY import
                     (held by analysis.boundary in check.sh)
             ┌───────────────────▼───────────────────────────┐
   GUARDED   │  engine/kernel.py — visible/get/create/act/   │  every call decided
             │  edit/delete + pure decide()/affordances()    │  by the rule base;
             │  refusals: typed Denied naming the rule       │  edits decided twice
             └───────────────────┬───────────────────────────┘
             ┌───────────────────▼───────────────────────────┐
   ANALYZED  │  rulesets/helpdesk/ — 14 rules from 7 tickets │  Z3 gate: 13 ∀ +
             │  (TICKETS.md), frozen safety.yaml/features    │  9 ∃ + 42 steps
             └───────────────────────────────────────────────┘
```

## Run it

```bash
./check.sh                                    # everything (5 stages)
../rule-driven-cms/.venv/bin/python app.py    # serve http://127.0.0.1:8810/
```

Switch personas in the sidebar: `dana`/`priya` (customers, acme), `omar`
(customer, zephyr), `sam`/`quinn` (agents), `noor` (lead), `postbot` (the
mail robot). Watch the queues repartition per persona — the list is the
read rule — and press a locked action to get the named refusal toast.

## What to look at

| Artifact | Why |
|----------|-----|
| `TICKETS.md` | The product spec in English; every rule/property names its ticket |
| `rulesets/helpdesk/rules.yaml` | The program: 6 denies, 8 allows, 3 projections. Note the *absent* containment denies — tight allows + default-deny, proven by the gate |
| `rulesets/helpdesk/safety.yaml` | The frozen gate, both directions, incl. 5 containments that have no deny rule |
| `app.py` | The free layer: custom "SLA breached" cross-state queue, "Assign to me", locked-action disclosures — zero policy |
| `bypass_variant/` | The three-line shortcut the boundary lint must refuse (check.sh stage 4 requires the FAIL) |
| `tests/test_relay.py` | Model agreement over all 19,200 situations; kernel refusals by name; forged HTTP requests bouncing off the kernel |
| `DEVLOG.md` | The honest journal: predictions, the round-1 PASS, frictions, the default_deny UX tension |

Research write-up: `research/15-kernel-boundary-free-ui.md`.
