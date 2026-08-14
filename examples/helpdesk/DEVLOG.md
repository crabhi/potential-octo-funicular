# Relay DEVLOG — the kernel-boundary episode, honestly

The journal of building `examples/helpdesk/` after the developer redirected
the architecture (2026-08-14): *"figure out a better way than a generic UI —
the developer builds the UI in htmx; keep the verified boundary at a
class/function-level API; customisability of the UX is crucial."* Recorded
per guardrail 7: predictions before runs, real analyzer output, dead ends
kept.

## Round 0 — the redirect, and what it cost the engine

Guardrail 10 went into CLAUDE.md first, then the engine grew the boundary:

* `engine/kernel.py` (~200 lines, domain-free): the only path to state.
  Reads and mutations decided by the rule base before the store is touched;
  refusals are typed `Denied` values carrying the rule; `decide()` /
  `affordances()` are pure queries for any UI to render however it likes.
* The JSON API and the old generic UI became thin adapters over one shared
  kernel — the generic UI is now officially *scaffolding* (a diagnostic
  rendering of the rule base), not a product surface.
* `analysis/boundary.py`: the mechanical hold. App code imports
  `engine.kernel` and nothing beneath it; sqlite3 and reach-around
  attributes are named CI failures. Honest scope: Python has no
  package-private, so this is a lint plus name-mangling, not a proof —
  the by-construction version is a process boundary.

**The kernel refactor closed note 14's sharpest gap.** Edits are now
decided twice: on the current row *and* on the row as it would become.
Cost: 6 lines in the kernel, 9 in the pure executor (model and
implementation must agree). Every existing gate — CMS, tickets,
receivables, Flowdeck — replayed green. The taskboard's documented
"member could re-team a task by editing `team`" hole is retro-closed by
the same change.

## Round 1 — predictions, then the analyzer

Predictions written before the first run:

* **P-a: zero dead rules.** The five containment denies (nothing deleted,
  staff never reopen, only leads close, customers never touch staff
  states, mailbot scope) were *omitted up front* — note 14's janitor
  lesson says tight allows + default-deny make them provably dead. The
  gate's S-properties (S4, S6, S11, S12, S13) prove each containment
  universally instead.
* **P-b: gate green on round 1.**

Real output: `VERDICT: PASS (0 findings)` — 14 rules effectual, 13/13
safety, 9/9 witnesses, 7 transitions live, 42/42 feature steps, in ~0.2 s.
Both predictions held.

Honest caveat: this is the third domain by the same author, with two
DEVLOGs of scar tissue. Round-1-green is evidence that the *discipline
transfers as method knowledge*, not that the gate is superfluous — the
taskboard's round 2 (two real authorization holes) is what this same
author produced one domain ago. The gate stays frozen precisely for the
author who hasn't read the DEVLOGs.

## What the free UI layer bought (and what it couldn't touch)

`app.py` is ~500 lines of hand-written htmx UI, and none of it is policy:

* A cross-state **"SLA breached" queue** with per-persona counts — a
  product view the reflected generic UI cannot invent (it only knows
  lifecycle columns). Pure presentation over `kernel.visible()`.
* **"Assign to me"**, severity chips, org-prefilled forms, toasts, partial
  swaps — UX taste, freely editable, rules untouched.
* Locked actions are a disclosure list naming the refusing rule, still
  pressable — a different affordance philosophy than the generic UI's
  greyed buttons, implemented against the same `kernel.affordances()`.

The tests forge what the UI never renders: postbot POSTs `triage`, quinn
POSTs `resolve` on someone else's case, dana POSTs `org=zephyr` on her own
case. All three come back 403 with the rule named. **Hiding a button
changes nothing; that is the whole point of the boundary.**

Seeding runs through the kernel as the real personas, so the demo data
cannot lie: seed case 6 breaches its SLA before resolution, and the seed
*had* to route its resolve through the lead — `breach_needs_lead` refused
sam during seeding. The rules govern even the fixtures.

## Frictions and open questions (the honest list)

1. **default_deny flattens refusal UX.** Omitting dead containment denies
   is right by the analyzer, but the robot's refusal toast now reads
   `default_deny: no rule allows this` instead of a stakeholder sentence
   about robots. The vocabulary is sound but the *error message* lost
   ticket language. Open DX idea: refusals could cite the nearest allow
   and why it didn't fire ("mailbot_files grants open, reply — not
   triage"). Solver-computable; not built.
2. **The lint is conservative by construction.** It refuses attribute
   names like `.store` anywhere in app code — a false-positive risk
   accepted for a research prototype; a real deployment wants module
   visibility or a process boundary.
3. **Two decisions per edit ≠ transactionality.** The kernel decides
   pre- and post-state, but a concurrent writer between decide and write
   is out of scope here (single SQLite connection); the P3 conformance
   harness is where that class of question lives.
4. **The free layer has its own plumbing bugs — and they stayed free.**
   `hx-vals` JSON quoting in f-strings is fiddly, and htmx refuses to swap
   4xx responses by default, so the kernel's honest 403 toast silently
   never rendered until a `htmx:beforeSwap` opt-in was added (caught by a
   screenshot, not by any gate — correctly so: *nothing was at stake but
   pixels*; the forged-request tests proved the refusal itself all along).
   The hour's plumbing time went entirely to presentation, none to policy.
   That is the intended asymmetry.

## Round 2 — the thread and the evidence (multi-entity, 2026-08-14)

The developer's next redirect: *"Rules covering multiple entity types is a
must. Comments and attachments are context-sensitive."* The engine grew
`children:` + `context:` (research note 16); Relay grows HD-8 (the case
thread) and HD-9 (evidence) as child entities of the case, with
`parent.state` and `parent.same_org` imported into their vocabularies.

Predictions written before the first analyzer run on the extended rule base:

* **P-c: zero dead rules, again.** Same discipline, fourth domain slice:
  the new containments (comments never edited/deleted, only leads redact,
  robot never reads the thread, attachments never deleted, removal is
  author-or-lead) again have NO deny rules — tight allows + default deny,
  proven by S17/S18/S19/S23/S24/S26. The one overlap that worried me on
  paper: `fresh_evidence_only` (attach on resolved|closed) vs
  `sealed_thread` (non-read on closed) — they intersect at attach+closed,
  but each has territory of its own (attach+resolved; remove/redact+
  closed), so neither should be dead.
* **P-d: round-1 PASS**, existing 13 S + 9 P untouched and still green.
* **P-e: zero engine domain lines** for the second time — `children:`,
  `context:`, `parent.*` are generic engine vocabulary now; nothing in
  the engine says comment, attachment, thread or seal.
* **P-f (friction, predicted):** the pure executor tracks ONE live item
  per entity, so scenarios that need two comments alive at once ("dana's
  public comment stays readable next to sam's hidden internal note")
  cannot be written as one feature — the feature files will show ordering
  workarounds. Acceptable for a gate; noted as an executor limit.

Real output (recorded after the run):

```
rules: 33 (16 deny, 17 allow) | roles: 5 | entities: 3 |
situation space: 37200 (case: 19200, comment: 12000, attachment: 6000)
   ok: all 33 rules are effectual (each changes at least one decision)
   ...29/29 safety ok, 16/16 witnesses ok...
   ok: 11 transitions live, all 9 states reachable, gated entries respected
   ...75/75 frozen feature steps ok (7 features)...
VERDICT: PASS (0 findings)
```

All four predictions held. P-c: neither seal rule is dead — the analyzer
confirmed each keeps unique territory. P-d: the 13 case S-properties and 9
case witnesses are byte-identical and still green; the case's 19,200
situations decide exactly as before (the exhaustive agreement test pins
this). P-e: `git diff` on the engine for this episode shows the
multi-entity mechanism only — no Relay vocabulary anywhere in it. P-f: the
predicted friction is visible in `feat_thread` — dana's internal-note
read-denial had to be aimed at *the latest* comment (the executor holds
one live comment), so the feature reads slightly out of story order.

Two things the round taught that were NOT predicted:

* **The witness situations got more interesting for free.** P13's witness
  is `read, parent.state: closed` — the solver picked a closed case to
  prove the thread survives closure. The parent-context atom turned a
  liveness property that used to be unstatable ("readable AFTER the
  parent moved on") into a one-liner.
* **`deny_inactive` was the only existing rule touched** — it gained
  `entity: [case, comment, attachment]`. Without the tag, a deactivated
  account could have posted comments: *the extension default (rules apply
  to the root only) fails safe for allows but fails OPEN for global
  denies.* Worth a lint some day: a deny mentioning only actor.* atoms
  probably wants every entity. Recorded as falsifier ME-5 in note 16 —
  and pinned mechanically the same hour: S28/S29 ("deactivated accounts
  can do nothing to threads/evidence") joined the gate, and the negative
  direction was verified by temporarily untagging the deny: the analyzer
  produced counterexamples for both properties plus a feature-step
  failure, exactly the trap the untagged rule base would have fallen
  into. (That verification run also cost an honest 10 minutes: restoring
  the tag with `git checkout` on the not-yet-committed file reverted the
  whole day's rule edits — re-applied from the session context. Commit
  before you experiment on yourself.)

## The scoreboard entry

* Domain vocabulary added to the engine for Relay: **0 lines** — the
  note-14 transfer-cost prediction (tickets ~0 → receivables ~100 →
  Flowdeck ~60 → next domain 0) **confirmed**.
* Architecture added (developer-directed, domain-free, reusable): kernel
  ~200 lines + lint ~110 lines.
* Rules 14, gate 13 S + 9 P + 2 gated entries + 42 frozen steps; analyzer
  round ~0.2 s; situation space 19,200, exhaustively backend-agreed.
* App: ~500 lines of UI nobody needs to review for policy; 12 tests;
  5-stage check.sh, all green.
