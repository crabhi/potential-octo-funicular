# Note 16 — Rules across entity types: children with parent context

**Status:** shipped (engine `children:`/`context:` + Relay HD-8/9).
Follows note 15 (kernel boundary, free UI). Developer directive
(2026-08-14): *"Rules covering multiple entity types is a must. Comments
and attachments are context-sensitive, for example. Explore this."*

## The wall this removes

Note 15's deck stated the limitation honestly: **one entity per rule
base**. Relay's cases fit one; case comments and attachments would force
either N separate rule bases *joined by the client*, or engine work. The
client-join option is not merely ugly — it is architecturally forbidden by
guardrail 10: whoever computes "may dana post here?" from two rule bases
plus a join IS an enforcement point, and the whole point of the kernel is
that the UI never is one. So: engine work.

The essence of the problem is that a comment's legality is
**context-sensitive**: it depends on the state and tenancy of the *case it
belongs to*, not just on the comment. "No comments on a closed case",
"the org wall extends to the thread", "internal notes are staff-only" are
all rules *about a relation* between two entity types.

## The design

One rule base, N entity types. The top level of the file stays the ROOT
entity unchanged (every existing rule base is the degenerate case); child
entities are declared under `children:` with their own states, fields,
projections and lifecycle. Two mechanisms carry all the new power:

* **`context:` — the child's window onto its parent.** Opt-in, atom by
  atom, because the situation space is a budget: `state` imports
  `parent.state` as an enum (a stored child always has a live parent, so
  no "none"), `is_author` imports "is the actor the PARENT's author?",
  and any parent projection name imports it computed against the parent
  row (`parent.same_org`, `parent.sla_breached`). A child with an empty
  context is legal and simply context-free.
* **The kernel does the join.** `create(actor, fields, entity="comment",
  parent_id=case_id)` loads the live case row and decides with it;
  reads, transitions, edits and `visible(actor, entity=, parent_id=)`
  all likewise. The client cannot compute context wrong because the
  client never computes it — the same argument as note 15's boundary,
  extended to relations.

Rules and gate properties carry an `entity:` tag (name or list),
**defaulting to the root** — so growing children touched zero existing
rules, zero frozen gate lines. The decision semantics is unchanged and
per-entity: only the rules tagged for an entity apply to its situations.

Deliberate limits, stated up front: one level of nesting, exactly one
parent per child, and **no aggregates** — a parent rule cannot see its
children ("close only if no open comments" is not expressible). See the
falsifiers.

## What was built

Engine (all of it domain-free; single-entity rule bases load unchanged —
cms, taskboard and the old Relay gates replayed green before anything new
was written):

```
rulebase.py   Entity class; per-entity vocabularies; entity-tagged rules
kernel.py     entity=/parent_id= on every call; the parent join lives here
store.py      one table per entity (items_<child> + parent_id); cascade
features.py   one live item per entity; child steps join the live parent
analyze.py    every check per entity; gate props tagged like rules
```

Relay (`examples/helpdesk/`) grew HD-8 (the thread) and HD-9 (evidence):
comment and attachment entities, org walls and seals via `parent.*`
context, internal notes, redaction and removal tombstones. Numbers: 33
flat rules (16 deny / 17 allow) over 3 entities; situation space **37,200**
(19,200 + 12,000 + 6,000), exhaustively two-backend agreed; frozen gate
29 ∀ + 16 ∃ + 4 gated lifecycle entries + 75 feature steps; analyzer
round-1 **PASS** with the pre-registered predictions held (DEVLOG). The
htmx UI renders the thread and evidence from kernel lists and affordances;
forged child requests (a customer posting `internal=yes`, the robot
redacting, posts into a closed case) come back 403 naming the rule.

## Findings

1. **Context-sensitivity costs one atom.** The entire "closed means
   closed" story for two child entities is one rule:
   `parent.state == "closed" and action != "read"` tagged
   `[comment, attachment]`. It seals posting, redaction, attaching and
   removal in one clause, *live* — close the case mid-session and the
   very next post meets the deny — and P13 proves the record stays
   readable. Compare the industry-standard alternative: a `sealed` flag
   denormalized onto every child row, plus the sync bugs it breeds. The
   child rules read the live parent, so there is nothing to sync.
2. **The extension default fails OPEN for global denies — caught, then
   pinned.** Untagged rules apply to the root only. That is right for
   allows (a child grants nothing by silence) but wrong for actor-only
   denies: `deny_inactive` without an entity tag would have let a
   deactivated account post comments. Found in round 2, fixed by tagging,
   and pinned mechanically: S28/S29 joined the gate and the negative
   direction was verified (untag the rule → 3 findings). Falsifier ME-5
   asks for the general lint.
3. **Liveness properties got stronger for free.** `parent.state` in a
   child's vocabulary makes temporal-sounding claims statable as pure
   possibility: "the thread of a CLOSED case is still readable"
   (P13) — previously unsayable, now a one-line witness the solver
   instantiates with a closed parent.
4. **Reads-as-decisions extends to relations cleanly.** An internal note
   is not "hidden" by the UI: `visible(dana, entity="comment",
   parent_id=...)` never contains it, `get()` by forged id raises the
   same named refusal, and the customer's rendered thread says
   THREAD (2) where staff see THREAD (3). The screenshot pair is the
   architecture in one image.
5. **The cascade is a real sharp edge, pinned but not solved.** Deleting
   a parent removes its children WITHOUT consulting the children's own
   delete rules (an engine test pins this behavior by name). Relay never
   meets it (nothing is deletable), but the composition rule is uncomfortable:
   *a child's immortality is only as strong as its parent's*. Worse, the
   per-entity gate cannot see it — no child situation is ever "allowed"
   on that path. The honest fix candidates: cascade-decides (the kernel
   decides `delete` for every child and refuses the whole cascade on any
   deny), or a load-time rule that a deletable parent may not have
   delete-denying children. ME-6.
6. **The executor's one-live-item-per-entity model held, barely** (the
   predicted friction P-f): gate scenarios needing two live comments at
   once must order steps so the interesting comment is the latest. Fine
   for a gate, a real limit for storytelling features.

## Falsifiers / next probes

* **ME-1 — aggregates will be demanded next.** "A case may not close
  while an attachment is quarantined", "escalate if ≥3 reopens" — parent
  rules over child sets. Not expressible, and not a syntax gap: an
  aggregate atom (`no_open_children`) is NOT a free boolean for the
  analyzer — it couples the parent's situation space to the child rules
  that govern how children reach states, i.e. a frame problem. A sound
  cut: kernel-computed aggregate projections treated as free booleans
  (runtime-sound, analyzer-conservative), with the imprecision stated.
  Build it when a ticket actually forces it.
* **ME-2 — depth and polymorphism.** Attachments on comments (two
  levels), or "reactions" attachable to either. The context mechanism
  composes on paper (grandparent atoms via the chain); the space budget
  and the kernel's join path are where it may crack.
* **ME-3 — field-level visibility.** A redacted comment is a readable row
  whose body the UI *chooses* to tombstone; rules cannot say "readable
  except the body". A rude free UI could render redacted bodies — today
  that is a presentation-layer trust hole, honestly outside the verified
  boundary. Field-level read rules would move it inside, at real
  vocabulary cost (per-field read atoms).
* **ME-4 — the join under load.** `visible()` on a child loads parent
  rows (cached per call, still N+1-shaped). Fold into KB2's reporting
  seam: a read path that applies the read rule per row at SQL speed.
* **ME-5 — the fail-open lint.** A deny whose condition mentions only
  `actor.*` atoms and is not tagged for every entity deserves an analyzer
  warning; finding 2 is exactly the bug it would catch at load time.
* **ME-6 — the cascade composition rule** (finding 5): implement
  cascade-decides or the load-time check, and write the domain that
  proves the current behavior wrong (deletable parent, "immortal" child).

## Verdict

Relations between ruled entities are now engine vocabulary, not client
code: **one rule base, N entity types, context flowing parent→child
inside the kernel**. The note-15 shape survives intact — rules → kernel →
free surfaces — and the new claim on top is narrow and tested: a child's
rules see its parent's live state, so context-sensitive policy ("sealed
threads", "walls extend to evidence", "staff-only notes") is written,
analyzed and enforced in the same vocabulary as everything else. What
stays honestly out of reach — aggregates, deep nesting, field-level
reads — is written down as falsifiers with designs attached, not wished
away.
