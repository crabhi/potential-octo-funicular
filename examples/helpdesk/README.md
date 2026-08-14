# Relay — a helpdesk with a FREE UI over a verified kernel

The guardrail-10 prototype: **the rules guard the interaction logic at a
class/function-level API; the UI on top is hand-written htmx and answers
to nobody.** UX customizability is a first-class requirement — so the
product surface is not generated from the rules; it is authored, styled
and reshaped freely, and it *cannot* weaken policy.

Since note 16, Relay is also the **multi-entity prototype**: the case, its
discussion thread and its evidence are three ruled entity types in ONE
rule base. Comment/attachment rules import the parent case's live state
and tenancy (`parent.state`, `parent.same_org`) — so "a closed case seals
its thread", "the org wall extends to evidence" and "internal notes never
reach customers" are rules the kernel enforces with a join the client
never performs.

```
             ┌───────────────────────────────────────────────┐
   FREE      │  app.py — hand-written htmx UI (~700 lines)   │  redesign at will;
             │  queues · toasts · thread · evidence · forms  │  no policy here
             └───────────────────┬───────────────────────────┘
                     from engine import kernel   ← the ONLY import
                     (held by analysis.boundary in check.sh)
             ┌───────────────────▼───────────────────────────┐
   GUARDED   │  engine/kernel.py — visible/get/create/act/   │  every call decided
             │  edit/delete + pure decide()/affordances(),   │  by the rule base;
             │  each with entity=; the kernel joins the      │  edits decided twice;
             │  parent row into every child decision         │  refusals typed+named
             └───────────────────┬───────────────────────────┘
             ┌───────────────────▼───────────────────────────┐
   ANALYZED  │  rulesets/helpdesk/ — 33 rules from 9 tickets │  Z3 gate: 29 ∀ +
             │  over 3 entities (case, comment, attachment); │  16 ∃ + 75 steps,
             │  child rules see parent.state/parent.same_org │  all per entity
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
read rule — then open case #1: staff see THREAD (3) with an internal
note; dana sees THREAD (2) — the note does not exist for her, not even by
forged id. Open the closed case #6: the thread and evidence render as a
read-only record, both forms replaced by `sealed_thread` by name.

## What to look at

| Artifact | Why |
|----------|-----|
| `TICKETS.md` | The product spec in English (now 9 tickets); every rule/property names its ticket |
| `rulesets/helpdesk/rules.yaml` | The program: 3 entities under one rule base; `children:` + `context:` are the whole relation mechanism. Note the *absent* containment denies — tight allows + default-deny, proven by the gate |
| `rulesets/helpdesk/safety.yaml` | The frozen gate, both directions, per entity — incl. S16/S25 (closing seals children) and S15 (internal notes stay inside) |
| `app.py` | The free layer: cross-state "SLA breached" queue, "Assign to me", the thread with internal notes and tombstones — zero policy |
| `bypass_variant/` | The three-line shortcut the boundary lint must refuse (check.sh stage 4 requires the FAIL) |
| `tests/test_relay.py` | Model agreement over all 37,200 situations (3 entities); kernel refusals by name; forged HTTP requests — incl. a forged `internal=yes` and a robot redact — bouncing off the kernel |
| `DEVLOG.md` | The honest journal: pre-registered predictions (rounds 1 and 2), the fail-open lesson (`deny_inactive` needed entity tags), frictions |

Research write-ups: `research/15-kernel-boundary-free-ui.md` (the
boundary), `research/16-multi-entity-rules.md` (the relations).
