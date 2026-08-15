# Formal guardrails — the developer's manual

*A development system for web applications in which you write
invariants, LLM agents write the code, and reasoning engines — not
humans — hold the code to the invariants.*

This manual is self-contained: it teaches the whole system, and
everything in it runs. The system ships as a reference implementation —
a generic rule engine with a solver-backed analyzer, an enforcement
kernel with a boundary lint, an agent-loop driver, and worked example
applications. The primary worked example, an expense-claims service
called **Clearance**, is built line by line in Part 1 and ships with a
one-command check; every transcript you will read is that tooling's
real output.

**Who this is for.** An experienced developer meeting this system for
the first time. You know web apps, SQL, CI, code review. You do not
need to know SMT solvers, model checkers, or temporal logic — the
system's core design decision is that *you never operate those
directly*; you write things they can check, and read what they answer.

**Scope.** The system targets ordinary product software: CRUD/API
handlers, authorization, tenancy, billing, workflows, schema
migrations, background jobs. Not kernels, crypto, or avionics. Every
component is sized for a normal product team and a normal CI budget.

---

## Part 0 — The system

### 0.1 The contract

The way you work today: intent lives in tickets and heads; code is the
durable artifact; humans review diffs to keep the two aligned. In this
system, every piece of that inverts:

| | Conventional development | This system |
|---|---|---|
| Durable artifact | the code | **the spec** (rules + gate) |
| Who writes code | you | LLM agents, freely |
| Who reviews code | humans, diff by diff | **nobody** — engines check it |
| What humans review | code | the spec, sentence by sentence |
| What a bug becomes | a regression test | **a frozen gate item** — a counterexample the gate refuses forever |
| Cost of regenerating code | prohibitive | cheap by design |

The one-line contract: **you state what must never and must always
happen; agents make something that does it; reasoning engines — not
you — hold the code to the statement.**

### 0.2 Three layers, one system

Different failure modes need different engines. The system has three
layers because a wrong authorization decision, a race between a
migration and a request, and a lazy agent "fix" that quietly deletes a
feature are three different animals:

```
 LAYER 1  Rules are the program            engine: SMT (Z3), exhaustive
          every single-request decision —  over the WHOLE situation space
          authz, tenancy, lifecycle,
          visibility, document discipline

 LAYER 2  Models before code               engine: model checker (Quint/
          everything that only goes wrong  Apalache/TLC), traces over
          across time and interleavings —  interleavings; conformance
          migrations, jobs, retries        harness against the real system

 LAYER 3  The frozen gate + agent loop     engine: the gate itself —
          all code agents write (UI, glue, frozen invariants + feature
          engine growth, repairs)          runs; counterexamples as the
                                           repair signal
```

Layer 1 is where you live day to day: features arrive as tickets and
become rules. Layer 2 is episodic: you reach for it when a design has
concurrency in it. Layer 3 is the meta-layer: it is *how any code gets
written at all* in this system, including the code beneath the other
two layers.

The composition rules — which layer owns which concern, and how the
layers hold each other — are Part 4, and they are what makes this one
system rather than three tools.

### 0.3 What it delivers

You should know what you are buying before reading 1,500 lines. The
characteristics, as they stand on the reference implementation:

- **Velocity**: a complete multi-tenant kanban SaaS is 7 tickets → 18
  rules → ~150 lines of YAML, zero application-specific imperative
  code — written in about an hour. The analyzer round-trip is ~0.2 s:
  you re-verify the whole application logic more cheaply than running
  one integration test.
- **Safety**: an application's full decision space — every combination
  of role, action, state and fact the rules can see — is checked
  *exhaustively*, against an independent solver encoding, on every
  change. A typical service has 3,000–40,000 such situations; checking
  is proof by enumeration, not sampling. On top of that sit universal
  safety properties, witness properties, and frozen end-to-end
  features.
- **DX**: the honest cost is discipline, not tooling pain: vocabulary
  is a budget you spend consciously, some refusals surface generically
  unless you name them, and anything the vocabulary can't say must go
  to a different layer *by decision, not by accident*.

The rest of the manual earns these claims, and Part 5 prices them.

### 0.4 What ships

The system's components, by the names this manual uses:

- **The engine** — a small, domain-free interpreter (~2,300 lines of
  Python including analysis, across all components) that loads a rule
  base and decides every request. It has no domain words in it; the
  same engine runs every application.
- **The analyzer** — the solver-backed reviewer
  (`python -m analysis.analyze <ruleset>`): dead rules, universal
  safety, witnesses, lifecycle, frozen feature runs. It can take its
  gate from a *pinned directory* (`--gate`), which is how specs stay
  frozen for agents.
- **The kernel** — the sole enforcement point (`engine/kernel.py`):
  a class/function-level API that decides every read and write against
  the rule base before touching the store. Held mechanically by a
  boundary lint (`python -m analysis.boundary <app>`).
- **The modeling toolchain** — off-the-shelf: Quint (with Apalache) for
  design models, TLC for liveness, plus a conformance-harness pattern
  for holding real systems to model invariants.
- **The loop driver** — a ~200-line harness that runs an agent against
  a frozen gate, feeds counterexamples back, and enforces the freeze.
- **The examples** — complete applications built this way, each with a
  one-command check (`check.sh`) that must pass in CI — including its
  *negative* stages: preserved buggy drafts the gate is required to
  keep failing.

---

## Part 1 — Layer 1: the rule base is the program

### 1.1 The mental shift

You stop writing `if` statements about who may do what. There is no
authorization middleware, no `can_edit?` helper, no scattering of
`WHERE org_id = ?`. Instead there is **one YAML file of rules** that IS
the application's interaction logic, executed by the generic engine,
and analyzed — every time it changes — by a solver that answers
questions no test suite can: *is any rule dead? does the safety
property hold in EVERY reachable situation? is the happy path still
possible at all?*

Three facts make this work:

1. **The decision is total.** Every (actor, action, resource) pair gets
   a decision from the same function. Deny rules override allow rules;
   **silence means deny**. There is no code path that forgets to check.
2. **The vocabulary is finite.** Rules speak only in enumerated facts —
   role, action, state, a handful of booleans. That is what makes
   exhaustive checking affordable, and it is a feature, not a limit:
   you choose the facts (a *budget*, see 1.3).
3. **One vocabulary end to end.** The ticket, the rule, the gate
   property, the runtime 403 and the analyzer counterexample all use
   the same names. When production refuses something, the response body
   names the rule; the rule names the ticket.

### 1.2 Tickets first

The worked example: **Clearance**, an expense-claims service. You start
where you always start — product English. Five tickets:

- **EX-1 Organizations** — employees and managers act only inside their
  own org; finance is central.
- **EX-2 Receipts** — a claim cannot be *submitted* without a receipt.
- **EX-3 Four eyes** — managers decide claims; managers file expenses
  too; **nobody ever decides their own claim**.
- **EX-4 Money** — only finance pays; finance does nothing else; a paid
  claim is a frozen record.
- **EX-5 The loop, and leavers** — rejection is revise-and-resubmit;
  after submission everything is the record; deactivated accounts do
  nothing.

Notice what these already are: quantified statements ("nobody ever…",
"only finance…", "nothing… ever changes"). Product owners speak in
∀ and ∃ natively. The system's bet is that you can keep those
quantifiers all the way down.

### 1.3 The vocabulary is a budget

Before rules, you declare what rules may talk about (the top of
`rules.yaml`):

```yaml
entity: claim

roles: [anonymous, employee, manager, finance]

states: [draft, submitted, approved, rejected, paid]

# The situation space is a budget: every boolean doubles it. Only
# `receipt` needs a has_ boolean (EX-2); org feeds a projection and
# amount is data no rule mentions — both opt out.
fields:
  - receipt
  - {name: org, has: false}
  - {name: amount, has: false}

actor_fields: [org]

projections:
  - {name: same_org, kind: actor_matches_field, actor_attr: org, field: org}

lifecycle:
  transitions:
    - {action: create,  from: none,      to: draft}
    - {action: submit,  from: draft,     to: submitted}
    - {action: approve, from: submitted, to: approved}
    - {action: reject,  from: submitted, to: rejected}
    - {action: revise,  from: rejected,  to: draft}
    - {action: pay,     from: approved,  to: paid}
```

Read this as a type declaration for the whole application:

- **The situation.** The engine derives a finite *situation space*:
  `actor.role × actor.active × actor.is_author × action ×
  resource.state × has_receipt × same_org`. For Clearance that is
  3,456 situations — small enough that "check them all" is a trivial
  instruction to a solver, and every claim below is over ALL of them.
- **`fields` and the `has_` opt-out.** A declared field gets an
  automatic `resource.has_<field>` boolean *unless you opt out*. Opt
  out aggressively: `amount` is data the rules never mention, so it
  costs nothing; `receipt`'s emptiness is EX-2, so it pays rent.
  Every boolean you admit doubles the space the solver sweeps and —
  more importantly — doubles what a reviewer must think about.
- **Projections** turn relations into booleans *at the boundary*. Rules
  never see "the actor's org string equals the resource's org field";
  they see `resource.same_org`. The engine computes the projection from
  the live rows; the rules stay propositional. This is the designed
  answer to "but my policy depends on data": you distill the dependency
  into a named boolean, once, and the name becomes part of the
  vocabulary budget.
- **The lifecycle is structural.** Transitions are not rules — an
  action fired from the wrong state is *illegal* (a shape error, HTTP
  409), before any rule runs. Rules answer "may they?"; the lifecycle
  answers "is that even a thing?". Keeping the two apart keeps rules
  short and keeps the state machine analyzable on its own.

There are also **assumptions** — facts about the world the solver may
rely on, which would otherwise generate false counterexamples:

```yaml
assumptions:
  - id: a_authors_file
    description: "Claims are authored by the people who may file them:
      employees and managers (EX-3)."
    holds: 'implies(actor.is_author, actor.role in ["employee", "manager"])'
```

Assumptions are dangerous exactly once: when they silently go stale
(you later allow a new role to create). The analyzer closes that hole
mechanically — it checks that every role that can `create` is an
assumable author, and fails otherwise.

### 1.4 Rules: deny, allow, and silence

The rules themselves — all ten, this is the entire application logic:

```yaml
rules:
  # ---- denies ----
  - id: deny_inactive
    description: "EX-5: a deactivated account can do nothing at all."
    effect: deny
    when: 'not actor.active'

  - id: org_walls
    description: "EX-1: employees and managers act only inside their own
      organization — reading included, and a claim can never be filed
      into another org."
    effect: deny
    when: 'actor.role in ["employee", "manager"] and not resource.same_org'

  - id: receipt_required
    description: "EX-2: no receipt, no submission."
    effect: deny
    when: 'action == "submit" and not resource.has_receipt'

  - id: no_self_decision
    description: "EX-3: nobody decides their own claim — managers file
      expenses too, and someone else approves them."
    effect: deny
    when: 'action in ["approve", "reject"] and actor.is_author'

  - id: the_record_is_sealed
    description: "EX-4 + EX-5: drafts are the only thing you edit or
      delete; everything after submission is the record."
    effect: deny
    when: 'resource.state != "draft" and action in ["edit", "delete"]'

  # ---- allows ----
  - id: staff_file
    effect: allow
    when: 'actor.role in ["employee", "manager"] and action == "create"'

  - id: author_maintains
    effect: allow
    when: 'actor.is_author
           and action in ["read", "edit", "delete", "submit"]'

  - id: author_revises
    effect: allow
    when: 'actor.is_author and action == "revise"'

  - id: manager_reviews
    effect: allow
    when: 'actor.role == "manager"
           and action in ["read", "approve", "reject"]'

  - id: finance_pays
    effect: allow
    when: 'actor.role == "finance" and action in ["read", "pay"]'
```

The semantics you must internalize:

- **Deny overrides allow.** `author_maintains` grants `edit` broadly;
  `the_record_is_sealed` carves the seal out of it. Order between
  denies matters only for *which name* surfaces in the refusal.
- **Silence denies.** No rule mentions `anonymous`. No rule says
  "employees never approve". No rule says "nothing touches a paid
  claim". All three are true anyway — `default_deny` — and the gate
  will *prove* them (1.6).
- **Every rule is a stakeholder sentence.** `description` is not a
  comment; it is what the product owner reviews, and it names its
  ticket. Reviewing the spec means reading these sentences against the
  solver's findings — never reading agent diffs.

### 1.5 The two disciplines (when to write a deny, when not to)

This is the craft heart of Layer 1:

**Role containment: tight allows, no deny, prove it with the gate.**
"Employees never approve", "finance only reads and pays", "the public
sees nothing" — do NOT write these as denies. The tight allows above
already make them true, so a deny would be *provably dead* — the
analyzer will fail it as noise (see 1.9 — this is not hypothetical;
it is a required stage of Clearance's own check). Instead you pin each
containment with a universal gate property (S1, S4, S10 below), which
holds forever regardless of how the allows evolve.

**State seals: broad allow + carving deny.** For "nothing edits the
record after submission" you *could* scope `author_maintains` down to
drafts and let silence deny the rest. Deliberately don't: write the
broad allow and the explicit `the_record_is_sealed` deny. The deny is
live (the analyzer proves it changes decisions), and — decisive for
UX — **the refusal has a name**. When a user hits it, the 403 carries
`the_record_is_sealed` and its stakeholder sentence, not a generic
`default_deny`. Named denies are error messages you can ship.

The trade is exactly that: containments-by-silence surface as
`default_deny` (acceptable for actions no legitimate user ever tries —
finance clicking "approve" has no UI affordance to begin with); seals
on the hot path deserve names.

### 1.6 The gate, directions 1 and 2 (`safety.yaml`)

The rules say what the system does. The gate says what must be true of
it — deliberately redundant, the way double-entry bookkeeping is
redundant. Direction 1: universal safety, quantified over EVERY
situation the rules allow:

```yaml
safety:
  - id: S4_only_managers_decide
    description: "EX-3: approve and reject belong to managers only."
    requires: 'implies(action in ["approve", "reject"],
                       actor.role == "manager")'

  - id: S7_paid_is_forever
    description: "EX-4: a paid claim admits nothing but reading."
    requires: 'implies(resource.state == "paid", action == "read")'

  - id: S10_finance_contained
    description: "EX-4: finance reads and pays — the blast radius of a
      compromised finance account."
    requires: 'implies(actor.role == "finance", action in ["read", "pay"])'
```

Read `S10` again: it is a *security posture statement* — "here is the
worst a stolen finance credential can do" — proved, not hoped. Note
also `S7`: there is no rule about paid claims at all; immutability
falls out of tight allows plus the lifecycle, and S7 pins it so no
future rule can unpin it silently.

Direction 2: possibility. **A gate with only safety properties is a
trap** — the safest system does nothing, and an agent (or a hasty
colleague) under safety-only pressure will happily "fix" a violation
by deleting the feature. Every gate must also state what must remain
possible:

```yaml
possibility:
  - id: P2_claims_can_get_paid
    description: "EX-4: the flow can actually finish — someone can pay."
    witness: 'action == "pay"'

  - id: P3_managers_expense_too
    description: "EX-3: a manager can submit their own claim — the
      four-eyes story is not vacuous."
    witness: 'actor.is_author and actor.role == "manager"
              and action == "submit"'
```

And structural jurisdiction over the lifecycle itself — "no future
feature may add a shortcut into `paid`":

```yaml
lifecycle:
  only_into:
    paid: [pay]
    approved: [approve]
```

### 1.7 The gate, direction 3 (`features.yaml`)

Frozen end-to-end scenarios, replayed on every change — first against
the pure decision engine in CI, then over real HTTP. The crucial
convention: **refusals are expected BY NAME.** A feature step that
expects `denied_by: receipt_required` fails if the submission is
allowed *and* fails if it is denied by anything else — so a deleted
deny cannot hide behind another deny that happens to overlap.

```yaml
features:
  - id: feat_four_eyes
    steps:
      - {actor: mia, action: create,
         set: {org: acme, amount: "412.00", receipt: "hotel.pdf"},
         expect: allow, state_after: draft}
      - {actor: mia, action: submit, expect: allow, state_after: submitted}
      - {actor: mia, action: approve, expect: deny,
         denied_by: no_self_decision}
      - {actor: fern, action: approve, expect: deny,
         denied_by: default_deny}
      - {actor: mo, action: approve, expect: allow, state_after: approved}
      - {actor: mia, action: pay, expect: deny, denied_by: default_deny}
      - {actor: fern, action: pay, expect: allow, state_after: paid}
```

Features are where liveness gets *concrete*: S-properties say paying is
finance's alone; `feat_four_eyes` proves a real claim actually reaches
`paid` through real actors. Safety, possibility, features — three
mutually redundant directions, and the redundancy is the point.

### 1.8 Run it

```bash
cd examples/approvals && ./check.sh
```

Stage 1, the analyzer, real output:

```text
== rule-base analysis: .../approvals/rules.yaml ==
rules: 10 (5 deny, 5 allow) | roles: 4 | entities: 1 | situation space: 3456
-- dead rules (does each rule ever change a decision?) --
   ok: all 10 rules are effectual (each changes at least one decision)
-- assumptions: every role that can create must be an assumable author --
   ok: creating roles ['employee', 'manager'] are all assumable authors
-- safety: must hold in EVERY allowed situation --
   ok   S1_no_anonymous
   ...
   ok   S10_finance_contained
-- possibility: must hold in SOME allowed situation --
   ok   P3_managers_expense_too  witness: {role: manager, action: submit,
        state: draft, active: true, is_author: true, has_receipt: true,
        same_org: true} (by author_maintains)
   ...
-- lifecycle: every state reachable, every transition usable --
   ok: 6 transitions live, all 5 states reachable, gated entries respected
-- feature runs (pure decision engine, frozen scenarios) --
   ok   feat_expense_flow (12 steps)
   ok   feat_four_eyes (7 steps)
   ok   feat_rejection_loop (10 steps)
VERDICT: PASS (0 findings)
```

Learn to read the possibility lines: each `ok` carries a **witness** —
a concrete situation the solver found, with the granting rule named.
`P3`'s witness is a manager, author of their own draft, with a receipt,
submitting — granted by `author_maintains`. Witnesses are how you spot
"passes for the wrong reason" at a glance.

This run costs a fraction of a second. You will run it the way you run
a type checker.

### 1.9 What failure looks like (and why you preserve it)

Clearance's first draft had employees-only filing. Its remains are
preserved in `rulesets/approvals-round1/`, and `check.sh` *requires*
it to keep failing against the frozen gate:

```text
-- dead rules (does each rule ever change a decision?) --
   FAIL DEAD deny rule 'no_self_decision': it never refuses anything
        that another rule would have allowed
-- safety: must hold in EVERY allowed situation --
   ok   S5_no_self_decision
   ...
-- possibility: must hold in SOME allowed situation --
   FAIL P3_managers_expense_too: IMPOSSIBLE — no allow rule ever grants it
-- feature runs --
   FAIL feat_four_eyes: step 1 (mia create): expected allow, got deny
        (rule: default_deny)
VERDICT: FAIL (3 finding(s))
```

Study this transcript; it teaches three permanent lessons.

1. **S5 still passes.** "Nobody decides their own claim" holds
   *vacuously* in the buggy draft — nobody can author-and-decide
   because managers can't author at all. A safety-only gate would have
   said the four-eyes ticket was fully satisfied. Only the possibility
   direction (`P3 IMPOSSIBLE`) and the dead-rule check expose that the
   feature does not exist. **Gates need both directions** — this is
   the single most transferable lesson in the manual.
2. **The dead-rule check is a spec review.** A dead deny is not
   harmless clutter; it is the solver telling you "this sentence of
   your spec is not doing anything" — which either means the sentence
   is redundant (delete it) or, as here, the world it guards against
   is unreachable *and that unreachability is itself the bug*.
3. **Findings are the currency.** Nothing here is a stack trace. Every
   failure names a rule, a property, or a step, in the vocabulary of
   the tickets. This is what the product owner reviews. It is also,
   verbatim, the repair signal an agent gets in Layer 3.

The bug's fix was a *requirement* fix (managers expense too — new allow
`staff_file`, updated assumption, new witness P3), and the broken draft
became a permanent regression: the gate that caught it must keep
catching it, forever, in CI. **Every counterexample becomes a frozen
gate item** — you will meet this ratchet again in every layer.

### 1.10 Serving it: the kernel and the free UI

The rule base decides; something must enforce. That something is the
**kernel** — a small, generic, class/function-level API that is the
*only* thing application code may import:

```python
from engine import kernel

k = kernel.boot("rulesets/approvals", "app.db", today="2026-08-15")
rows = k.visible(actor)                      # the read rule, applied
row  = k.create(actor, {"org": "acme", "receipt": "taxi.pdf"})
row  = k.act(actor, "submit", row["id"])     # lifecycle transition
d    = k.decide(actor, "approve", row)       # pure query, for affordances
try:
    k.delete(actor, row["id"])
except kernel.Denied as e:
    e.rule.id                                # 'the_record_is_sealed'
```

The load-bearing properties:

- **Every read and every mutation is decided before the store is
  touched.** `visible()` *is* the read rule — there is no separate
  "list" logic to keep consistent with it. This closes the classic
  IDOR-by-enumeration hole by construction.
- **Refusals are typed values.** `Denied.rule` carries the rule — id
  and stakeholder sentence — so the HTTP layer's 403 body and toast
  are one line of rendering, in gate vocabulary.
- **Edits are decided twice**: on the current row ("may this actor edit
  this thing?") and on the post-edit row ("may it become this?"). A
  customer re-tenanting a resource by editing its `org` field is
  refused by the same `org_walls` that guards reads. If your framework
  decides edits once, it has this hole.
- **The UI above the kernel is FREE.** Hand-written htmx, React,
  anything — styled and reshaped without limit, because it *cannot*
  weaken policy: hiding a button changes nothing about what the kernel
  permits, and a forged request for a hidden button gets the same named
  403. The UI renders affordances by *asking* (`k.decide(...)` /
  `k.affordances(...)` probes) rather than by re-deriving policy — the
  moment UI code computes policy, it is an enforcement point, and
  enforcement points are exactly what you have one of.
- **The boundary is mechanical, not conventional.** A lint
  (`python -m analysis.boundary <app dir>`) verifies app code imports
  `engine.kernel` and nothing beneath it, and each application's CI
  keeps a three-line bypass variant that the lint is *required to
  fail*. A boundary nobody can violate quietly is worth ten style
  guides.

The reference implementation includes a complete helpdesk product built
this way — a ~700-line hand-written htmx UI (cross-state SLA queues,
assign-to-me, discussion threads with staff-only internal notes) with
zero policy in it, over exactly this kernel. The same case, two
viewers — staff see THREAD (3) with an internal note; the customer sees
THREAD (2), and the note does not exist for her even by forged id,
because `visible()` is the read rule:

| staff view | customer view |
|---|---|
| ![the thread as staff](slides/img/relay-sam-thread.png) | ![the thread as the customer](slides/img/relay-dana-thread.png) |

And a refusal on the wire — the 403 toast naming its rule, straight
from `Denied.rule`:

![named 403 toast](slides/img/relay-denied-toast.png)

### 1.11 Relations: child entities and parent context

Real products are not one entity. A comment's legality depends on its
*case*: a closed case takes no new comments; the tenancy wall extends
to the thread. The wrong answer is N rule bases plus client-side
joins — whoever computes cross-entity context IS an enforcement point,
and the UI must never be one. The system's answer is `children:` +
`context:`. From the helpdesk's rule base — the case is the root
entity, and its thread and evidence are ruled children:

```yaml
children:
  - entity: comment
    states: [posted, redacted]
    fields: [body, internal]
    context: [state, same_org]     # imports parent.state, parent.same_org
    lifecycle:
      transitions:
        - {action: post,   from: none,   to: posted}
        - {action: redact, from: posted, to: redacted}
```

Child rules then speak about the parent — and the kernel joins the
live parent row into every child decision (create, read, edit, list),
so the context is always current:

```yaml
  - id: sealed_thread
    description: "A closed case seals its thread and its evidence."
    entity: [comment, attachment]
    effect: deny
    when: 'parent.state == "closed" and action != "read"'
```

```python
k.create(actor, {"body": "hi"}, entity="comment", parent_id=case["id"])
k.visible(actor, entity="comment", parent_id=case["id"])   # the thread
```

"A closed case seals its thread" is one atom, checked live — not a
`sealed` flag denormalized onto every child row, plus the sync bugs
that flag breeds.

Two sharp edges, both pinned by gates in the reference implementation —
respect them in your own rule bases:

- **Untagged rules apply to the ROOT entity only.** That defaults
  correctly for allows (fails closed) but is a trap for global denies:
  an actor-only deny like `deny_inactive` silently stops covering
  comments the day you add them — it **fails open**. Tag it
  (`entity: [case, comment, attachment]`) and pin it with per-entity
  gate properties, so untagging is a named finding, not a quiet hole.
- **Parent-delete cascades do not consult child delete rules.** A
  child's immortality is only as strong as its parent's. If children
  must be forever, the *parent* must be undeletable.

And one honest limit: rules can see the parent's state, never
aggregates over children — "close only if no open comments" is not
expressible today (Part 5 explains why that is a hard problem, not a
missing feature, and what the designed remedy is).

### 1.12 Day 2: the working loop

A new ticket arrives. The loop, which you will run in minutes, not
days:

1. **Write the ticket into `TICKETS.md`** in product English with its
   quantifiers intact.
2. **Spend vocabulary consciously.** New state? New projection? A
   `has_` boolean? Each admission is permanent review surface — prefer
   reusing existing facts; opt fields out of `has_` by default.
3. **Write the rules** — carving denies for hot-path seals (named
   403s), tight allows for containment.
4. **Extend the gate first or alongside, never after**: an S-property
   for each "never/always/only", a witness for each "can", feature
   steps for the scenario *including its expected refusals by name*.
5. **Run the analyzer.** Read every witness (not just the verdict
   line). A dead rule or an IMPOSSIBLE witness at this stage is the
   solver reviewing your spec — argue with it before any code exists.
6. **Ship.** No enforcement code to write — the kernel already enforces
   the new rules. UI affordances appear via the probe pattern. If the
   UX needs new surfaces, that is free-layer work (agent work, Layer 3).
7. **Freeze.** The new gate items never leave. Weakening the gate is a
   human-only, explicit act with a written reason.

### 1.13 What this layer refuses to do

Knowing the boundary is part of the skill. Not in the vocabulary, by
design: arithmetic and cross-row aggregates (sum of claims this month),
fuzzy matching, free-text inspection, field-level *visibility* (a
redacted comment's body is hidden by UI choice — the kernel guards the
row, not the column), true temporal ordering ("approved within 48h").
Some of these go to projections (a boolean distilled at the boundary,
like `sla_breached` from a date), some to Layer 2 (ordering,
concurrency), some stay deliberately client-side. The decision that
matters: **each exclusion is explicit and written down**, never
discovered in production.

### 1.14 The ledger

**DX** — the program you review is ~150 lines of YAML sentences per
entity; the solver reviews with you — a finding arrives with the
situation *and* the granting rule, so there is no debugger and no
log-diving; refusal UX is free (named 403s). The costs: naming
conventions (projections are resource-relative), probe placement (deny
names are declaration-order), and the vocabulary budget you manage by
hand. **Velocity** — a ticket is usually a handful of rules plus gate
lines; analyzer feedback in ~0.2 s; no enforcement code, ever.
**Safety** — exhaustive, not sampled: every property over every
situation, both directions frozen, boundary lint in CI, forged
requests hit the same kernel the buttons do.

---

## Part 2 — Layer 2: models before code

### 2.1 Bugs that live between requests

Layer 1 decides one situation at a time. A whole class of bugs does not
exist in any single situation: they live in the *interleavings* — a
schema migration backfilling rows while two app versions serve traffic,
a background job retrying against state another worker moved, two
requests racing a flag flip. No per-request rule can see them, no
matter how exhaustively you check it, because every individual decision
is correct; the sequence is what's wrong.

The worked example for this layer is the classic hard case: **rename a
column while the application serves traffic** (expand/contract, under
snapshot isolation, with a rolling deploy in flight). You will design
the protocol as a model first, then hold the real implementation to the
same invariants.

The principle: **model the design before the code exists.** The model
is a design document that fights back.

### 2.2 A worked model

The entire model is 270 lines of Quint — comparable to the design doc
you would have written anyway, except this one is executable. Its state
is the essence of the situation, including two *ghost variables* (state
the real system doesn't have, tracked purely so correctness is
statable):

```quint
var phase: int                   // migration phase
var dbO: int -> int              // committed value of column O per key
var dbN: int -> int              // committed value of column N per key
var ver: int -> int              // committed row version (SI conflicts)
var instVer: int -> int          // app instance -> app version (1 or 2)
var bf: (bool, int, int, int)    // in-flight backfill transaction
var logical: int -> int          // ghost: what the app believes k holds
var lastReadOk: bool             // ghost: false once any read was stale
```

Eleven actions cover the world: v1 instances write only the old column,
v2 instances dual-write, reads route by phase, the rolling upgrade is
nondeterministic, and the backfill is a genuine multi-step
snapshot-isolation transaction with first-committer-wins conflict
detection. The read is where the ghost gets armed:

```quint
action appRead = {
  nondet i = INSTANCES.oneOf()
  nondet k = KEYS.oneOf()
  val fromN = and { nState == COL_PRESENT, instVer.get(i) == 2 }
  val seen = if (fromN) dbN.get(k) else dbO.get(k)
  all {
    or { fromN, oState == COL_PRESENT },
    lastReadOk' = and { lastReadOk, seen == logical.get(k) },
    ...
  }
}
```

And then the part you actually author as the developer — the
invariants, which are one-liners:

```quint
// I1: no committed read ever returned anything but the logical value.
val invReadsCorrect = lastReadOk

// I2: after the read switch, while both columns live, they agree.
val invColumnsAgree =
  (phase == P_SWITCHED and oState == COL_PRESENT)
    implies KEYS.forall(k => dbN.get(k) == dbO.get(k))

// I3: reads never switch to N before every row is backfilled.
val invBackfillDoneAtSwitch =
  (phase >= P_SWITCHED) implies KEYS.forall(k => dbN.get(k) != NULL)
```

Note the division of labor, because it is the same one as Layer 1's:
**you state what must hold (three one-liners); the engine explores what
your design actually does.** The ghost-variable pattern is the craft
trick to learn — "no stale read, ever" becomes a boolean that any
action can falsify and an invariant can watch.

One more Layer-1 habit transfers verbatim: the model is *instantiated
twice*, `correct` (with the drain guard) and `broken` (without), and
the one-command check requires the broken one to fail:

```bash
echo "== simulate: broken protocol, no drain guard (expect: violation) =="
quint run migration.qnt --main broken --invariant invAll \
  --backend typescript --max-samples 20000 --max-steps 25 && {
    echo "ERROR: expected a violation in the broken config"; exit 1; } || true
```

A gate that has never failed is untested; every layer of this system
keeps a broken variant around to prove its checker still bites.

### 2.3 What the checker does to your design

Here is why this layer exists. Two successive versions of this
protocol *look* correct — a careful engineer would sign off on either
in design review. The checker refuses both, and each counterexample
corresponds to a real production failure mode:

1. **Drain guarded only at backfill start.** The first design requires
   "all instances upgraded" only before backfill. Counterexample: v2
   dual-writes fill the new column for every key, so the read switch's
   "backfill complete" condition is satisfied *without any backfill
   running* — while a v1 instance is still alive. It writes the old
   column post-switch; a reader returns a stale value. Fix: the drain
   condition must gate the read switch too.
2. **`WHERE full_name IS NULL` backfill is wrong under rolling
   deploys.** The second design backfills only rows with no new-column
   value. Counterexample: during the rolling window a v2 instance
   dual-writes key k, then a still-live v1 instance overwrites the old
   column only — N is non-NULL but **stale**, and an IS-NULL backfill
   never revisits it. The staleness survives the drain and the switch.
   Fix: backfill `WHERE new IS DISTINCT FROM old`, and gate the switch
   on "all rows in sync", not "all rows non-NULL".

Both counterexamples fall out of random simulation **in under a
second** and are confirmed symbolically. Read that against what these
bugs cost when found the usual way: each is a rare, load-dependent,
rolling-deploy-window data-corruption incident. Here each costs one
red trace, before any code exists. This is what design review by
adversarial search buys that design review by nodding cannot.

The fixes live in the model as annotations beside the guards they
added — the model *is* the design record. And this same protocol, with
the second bug re-planted, is Part 3's repair task: the layers feed
each other counterexamples.

### 2.4 The escalation ladder

A bounded check is not a proof, and the system is explicit about which
rung of assurance each artifact sits on. The ladder, as climbed for
this one protocol:

| Rung | What it asserts | Cost |
|---|---|---|
| 0 — random simulation | "30k traces found nothing" | seconds; found both design bugs in <1 s |
| 1 — bounded symbolic | all behaviors ≤12 steps, fixed 2×2×2 constants | `quint verify --max-steps 12` (Apalache/SMT), ~10–60 s |
| 2 — inductive invariant | every depth, fixed constants | a 7-conjunct hand-written strengthening + shape constraints; all three obligations verify in ~10 s |
| 3 — parameterized | every depth AND every key/instance count | an EPR encoding (mypyvy): verifies in 0.38 s; the tool can even *infer* a sufficient 9-clause invariant itself in 5.7 s |
| 4 — liveness under fairness | the migration always completes | TLC over the complete 623-state graph |

Rules for climbing it:

- **Climb only when the question demands it.** Rung 1 is the daily
  driver. Rung 2's craft is *strengthening* — the property you care
  about is rarely inductive by itself; the seven conjuncts (phase-shape
  coupling, "O carries the logical value while live", drain
  monotonicity…) are the protocol's real semantic content, and writing
  them teaches you your own design.
- **Negative controls must break the load-bearing guard.** Build the
  parameterized proof's negative control by weakening only the
  backfill guard and it *still verifies* — the protocol deadlocks
  instead of corrupting, a safety-preserving liveness bug. Reproducing
  the real failure requires breaking the switch guard too. Lesson: a
  negative control that doesn't fail the way the real bug fails is
  testing the wrong thing.
- **Liveness proofs can surprise you favorably.** You would expect this
  protocol's completion proof to need a bound on interference
  (adversarial writes keep dirtying rows, backfill starves — the
  classic story). It doesn't, and the reason is a genuine insight the
  prover hands you: after the drain, every interfering write is a
  dual-write, so interference *does the backfill's work*. Completion
  needs no interference assumption at all — only fairness of the
  deploy itself (drop rollout fairness and the checker hands you the
  stalled-deploy lasso). Either direction, the tool settles it.

The ∃-witness discipline from Layer 1 also reappears here as liveness:
the frozen gate for this protocol counts completion witnesses (can the
migration finish at all?) precisely because safety alone is gameable —
a protocol that can never switch reads satisfies every safety invariant
above.

### 2.5 Closing the model↔code gap: conformance

The model verified the *design*. Your production system runs *code*,
and the system's honest accounting says: **the model↔code boundary is
held by tests, and tests are sampling, not proof.** What Layer 2 adds
is that the sampling is *directed by the spec* — every check the
harness makes is a formal invariant instantiated on HTTP, same
vocabulary, traceable line by line.

The conformance harness is the shape to copy: a real API running as
**two versions simultaneously** (version skew is the point), a real
database, the real five-step migration
(`expand → install-trigger → backfill → read-switch → contract`), six
worker threads of mixed traffic, and the migration advancing in a
background thread. Each harness check names its formal counterpart —
I1 becomes

```python
if status == 200:
    assert body["name"] == self.expected[uid], (
        f"stale/wrong read via {base}: "
        f"expected {self.expected[uid]!r}, got {body['name']!r}")
```

and "no request observes a column that is gone" becomes an error-text
classifier (`is_schema_error`: a 5xx whose body says `does not exist`)
— which works because the API deliberately surfaces raw database error
detail *for the harness's benefit*. Design your systems to be
checkable: the observability the spec needs is part of the interface.

Here is the class of bug this harness catches in code that passes its
unit tests — **a TOCTOU race inside the *modern* instance**: v2 reads
the migration flags, decides which SQL text to build, then executes
it — two round-trips, not one transaction. If `contract` commits in
that gap, the request has already committed to SQL referencing a
dropped column. Note what did *not* go wrong: the predicted
trigger/backfill lost-update is impossible by construction (the
trigger recomputes inside the write's own transaction) — the real bug
was one level up, in request handling, where nobody was looking. The
fix (a ~150 ms global quiesce at the cutover instant, exactly the
atomic-rename pause production online-DDL tools take) is itself
design knowledge now. And the negative test stays forever:
deliberately skip the drain and the harness must reproduce the
anomaly — dozens of `column does not exist` errors per run — empirical
proof that the precondition is load-bearing, not decorative.

Two stronger bridges exist when you need more than invariant-directed
load, and the reference implementation demonstrates both:

- **Model-based testing** (spec drives app): `quint run --mbt` emits
  traces with the exact nondeterministic choices taken; an adapter
  replays each step as one HTTP call and asserts acceptance parity and
  observable-state parity — and replays the model's *counterexample*
  traces to confirm the live system refuses exactly the step the
  weaker design would have allowed, by rule name.
- **Trace validation** (app drives spec): record which actions the
  real app accepted, mechanically compile the log into a model run
  ending in `.expect(lastActionOk)`, and ask the checker "was this a
  legal behavior of the model?" — conformance checking from
  client-side logs, no instrumentation.

Both are cheap because of the ghost-variable pattern: one boolean
(`lastReadOk`, `lastActionOk`) carries the whole correctness story
across the seam.

### 2.6 The working loop and the ledger

When a design has concurrency in it — a migration, a job, a saga, a
cache — the loop is: write the model *instead of* the design doc
(same length, executable); state the invariants as one-liners over
ghost state; let simulation attack it (seconds); fix the design, keep
the broken config as a negative control; escalate rungs only where the
question demands; then hold the implementation to the same invariants
with a conformance harness whose every assertion names its formal
counterpart.

**DX** — Quint reads like code, not like set theory; the model doubles
as the design record (fixes annotated where they live); design
disagreements get settled by a tool instead of a meeting. **Velocity**
— a production-grade protocol bug costs one red trace, pre-code; the
whole model is a day's work and 270 lines; rung-1 checks fit in CI.
**Safety** — rung-labeled honesty: you always know whether you hold
sampling, bounded, inductive, parameterized, or liveness evidence, and
the ladder's upper rungs are real and priced (0.38 s any-size proofs
exist; so do hand-written strengthenings that take an afternoon). The
permanent tax is the model↔code seam — paid with spec-directed
conformance, never waved away.

---

## Part 3 — Layer 3: the frozen gate and the agent loop

### 3.1 You never review agent diffs

Layers 1 and 2 gave you specs machines can check. Layer 3 is what that
buys: **agents write and repair the code, and no human reads their
diffs.** What the human reads instead: the gate, the counterexamples,
and the round logs. The contract has four clauses, all mechanical:

1. **The spec is frozen for the agent.** Code edits cannot weaken the
   gate; spec edits are a human ceremony. This is the load-bearing
   rule — without it the agent optimizes the gate instead of the code.
2. **Counterexamples are the universal currency.** Checker traces (ITF
   JSON), failing feature runs, named 403s — all normalized into
   "violated invariant + concrete scenario" payloads that flow back to
   the agent.
3. **Green must be meaningful.** Prefer oracles with crisp completeness
   stories (model-checked bounds, exhaustive checks) over "N random
   runs found nothing"; layer them so the gaps of one are covered by
   another.
4. **Objective functions live outside the gate.** Performance and cost
   are optimized only within the feasible region the spec defines. The
   agent may make the system faster in any way it likes; it may not
   make it wrong.

And the staffing consequence: repairers are *deliberately cheaper
models* — the gate, not the model, carries the correctness burden.
Correctness spend goes into the gate once, not into per-task prompt
craft or premium-model tokens forever.

### 3.2 The freeze is mechanical

"The spec is frozen" is enforced by code, never by convention or
prompt. The loop driver's entire enforcement mechanism is a string
comparison of the file's tail — everything below a marker line — with
whole-file revert on mismatch:

```python
FROZEN_MARK = "==== INVARIANTS"

def frozen_region(text: str) -> str:
    idx = text.find(FROZEN_MARK)
    if idx < 0:
        sys.exit("frozen marker missing from protocol file")
    return text[idx:]

# ... after the agent runs:
after = PROTOCOL.read_text()
if frozen_region(after) != frozen_before:
    PROTOCOL.write_text(before)
    print(f"round {rnd}: SPEC EDIT DETECTED — reverted, round failed")
```

A round that touches the frozen region loses its code edits too — the
round is wholly discarded and the budget is spent. The prompt *also*
tells the agent not to touch the spec, but nothing depends on the
agent listening; that is the point.

The system uses three freeze mechanisms — pick per artifact:

| Freeze | Mechanism | Use for |
|---|---|---|
| region-in-file | marker line + tail string-compare + revert | a spec that lives beside the code it governs |
| everything-except-one-path | `git status --porcelain` + `git checkout --` on any path but the allowed one | letting an agent loose on one file of a real codebase |
| pinned gate directory | `analyze <edited rules> --gate <frozen dir>` | every Layer-1 rule base |

### 3.3 Anatomy of the loop

One driver, ~200 lines, four moving parts.

**The gate ladder**, run each round: typecheck → frozen feature runs
(`quint test`) → safety simulation over 30k traces **plus a
completion witness** → optionally a symbolic verification pass. The
witness clause is the anti-"safest system does nothing" mechanism, ten
lines of it:

```python
if ok:  # safety green: also require completion to be reachable at all
    m = re.search(r"featDone was witnessed in (\d+)", out)
    if not m or int(m.group(1)) == 0:
        ok = False
        out += "\nGATE FAILURE: migration completion (phase == P_DONE) " \
               "was never reached in any explored trace — the protocol " \
               "can no longer complete."
```

**The feedback**: on red, the failing stage's output tail plus the
counterexample trace (ITF JSON, trimmed to first 2 + last 10 states)
are formatted into the prompt. Machine-readable counterexamples are
what make the loop closable — the agent gets the exact violating
scenario, not a vibe.

**The agent**: headless, tools cut to the bone:

```python
cmd = ["claude", "-p", "--model", model,
       "--permission-mode", "acceptEdits",
       "--allowedTools", "Read,Edit"]
```

No shell, no file creation — Read and Edit, on one file, with the
prompt on stdin. The prompt itself is **entirely bug-agnostic**: it
explains the domain, states the rules of engagement ("Edit ONLY the
action definitions… Make the minimal protocol change… do not add
artificial guards that merely disable functionality"), and pastes the
counterexample. Nothing about the specific bug, ever.

**The audit trail**: every round writes the prompt, the agent's own
transcript, the resulting file, and the checker verdict to a per-round
directory. Rounds are replayable evidence.

Budgets are explicit: 4 rounds default, 30,000 traces per check,
timeouts per stage, exit 1 on budget exhaustion. A loop without a
budget is an agent with an unbounded bill.

### 3.4 Why the gate needs both directions: the same repair, twice

This is the system's central design lesson, and you can reproduce it
yourself with the loop driver and the migration protocol.

The task: Part 2's protocol with its second bug planted (IS-NULL
backfill + non-NULL switch check). The correct fix needs *two coupled
edits*; the trap is that one of them alone is sound-but-partial.

**Run 1 — safety-only gate.** The repairer fixes the switch guard
(`dbN != NULL` → `dbN == dbO`), with a correct explanatory comment —
and leaves the backfill criterion broken. Every safety invariant
holds; 30k traces clean; the symbolic pass agrees. The loop declares
victory. But the fix is partial: a row that went stale before the
drain is never re-copied and now **blocks the switch forever**. The
migration is safe and can no longer complete. *A safety-only gate
accepts a fix that trades away liveness* — the checker did its job;
the gate was underspecified.

**Run 2 — the gate grows both directions.** The frozen region gains a
completion witness (`featDone`) and two scripted feature runs — a
happy path, and an adversarial `staleRowRecoveryTest` that stages
exactly the pre-drain-staled row and demands the migration machinery
alone recover it. Same protocol, same model, same prompt. Round 1's
feedback is no longer a 22-state trace but a pointer at the exact
required behavior that stopped being possible:

```text
1) staleRowRecoveryTest failed after 1 test(s)
     Error [QNT513]: Cannot continue in `then` because the highlighted
     expression evaluated to false
      240:     .then(backfillBeginU(1))   // must be enabled for the stale row
```

The repairer produces the **full fix** — both edits, backfill
`N != O` and switch `N == O` — in one round, feature runs green,
completion witnessed in 84% of traces, symbolic pass clean.

| | safety-only gate | both-directions gate |
|---|---|---|
| gate contents | safety invariants only | + feature runs + completion witness |
| feedback to repairer | safety counterexample (ITF) | failing required-behavior run |
| outcome | sound but partial fix; latent liveness regression accepted | full fix, one round |

Zero prompt engineering separates the two outcomes. **With LLM
repairers, invest in gate strength, not natural-language steering —
the gate is what the system actually optimizes toward.** Notice also
that the stronger gate produces *better feedback for free*: the
failing feature run is a shorter, more targeted counterexample than
the raw trace. Well-chosen gate items are also well-chosen error
messages.

### 3.5 The objective outside the gate: the optimization loop

The same pattern pointed at performance instead of repair: the agent
may edit exactly one file of a real Rust web server; the gate (a
boundary lint plus the full policy and race-condition suite) is
frozen; a benchmark is the objective; an edit is accepted only if the
gate is green *and* throughput improves ≥10%. A four-round run looks
like this:

```text
baseline: 62.9 rps   (p50 248 ms, p95 287 ms)
round 1: GATE RED — reverted   (RwLock attempt, leftover Mutex ref: E0433)
round 2: ACCEPTED — 248.1 rps  (p50 64 ms; gate fully green)
round 3: gate green, 254.9 rps — below the 10% acceptance bar, reverted
round 4: GATE RED — reverted   (axum::serve::Listener refactor: E0405)
final: 248.1 rps — 3.94x speedup
```

Read the round pattern, because it is the whole value proposition:
two broken attempts absorbed by the gate at zero human cost; one
working-but-marginal micro-optimization rejected by the threshold
rather than accumulating churn; and the accepted edit fixed exactly
the two real performance defects, unprompted. 3.94× faster, never
wrong, nobody read a diff.

### 3.6 Boundaries by construction

The strongest freeze is the one the compiler enforces. Where the
language allows it, make bypassing the verified kernel a **compile
error**, not a lint finding. In Rust, protected operations require a
capability token only the kernel can mint:

```rust
#[non_exhaustive]
pub struct Grant<Op> {
    _op: PhantomData<Op>,
}

/// The kernel's one and only entry point. ... On success, returns a
/// Grant<Op> — proof, checked by the compiler at every call site that
/// needs one, that this decision was actually made.
pub fn require<Op: Operation>(identity: Identity, meta: ArticleMeta)
        -> Result<Grant<Op>, DeniedRule> {
    Op::decide(identity, meta)?;
    Ok(Grant { _op: PhantomData })
}
```

`Operation` is a sealed trait, so app code cannot invent a fifth
operation; `Grant` has a private field and `#[non_exhaustive]`, so it
cannot be forged; and both failure modes are **pinned compile-fail
tests**: forging a token is E0639, and holding *some* grant but not
*this* one (`do_publish(edit_grant)`) is E0308 — "I checked SOME
permission" stops compiling. Denials return a `DeniedRule` naming the
same invariant identifier the gate files use — the one-vocabulary rule
again.

Document the honest residue next to the types, whatever your language:
identity *freshness* is not the kernel's to guarantee (a stale cached
identity is a TOCTOU in the caller — Layer-2 territory); a handler can
call `require` and ignore the `Result` (a belt-and-suspenders lint
greps for that shape); `unsafe` is out of scope. Python's kernel
boundary (Part 1) is the same principle at lint strength; Rust buys
you the compiler. Use the strongest enforcement the language offers,
and *name* what remains convention.

### 3.7 Running your own loop: the ledger

The checklist: freeze mechanically (pick one of the three mechanisms);
gate both directions before the first round — 3.4's first run is what
happens otherwise; keep the prompt generic and permanent; restrict
tools to Read/Edit; log every round; make counterexamples
machine-readable and invariant-named; set a round budget; and when a
round produces a bad-but-green fix, the fix is a *new frozen gate
item*, never a better prompt.

**DX** — the review artifact shrinks from diffs to counterexamples and
round logs; every round is auditable after the fact; the failure modes
are named (`SPEC EDIT DETECTED`, `GATE FAILURE: ... can no longer
complete`) instead of discovered. **Velocity** — repair typically
converges in single-digit rounds (both worked repairs above took one);
gate stages run in seconds-to-minutes; cheaper models carry the work
because the gate carries the burden. **Safety** — the gate only
ratchets: historic bugs stay as frozen FAIL-required variants,
objectives cannot override correctness by construction, and the one
genuinely dangerous move (weakening the gate) is a human ceremony that
no agent can perform.

---

## Part 4 — Composition: one system

### 4.1 Which layer owns which concern

The routing decision you make on every requirement:

| The requirement sounds like… | It lives in… | Because |
|---|---|---|
| "Only X may…", "never…", "X sees only…" (one request decides it) | **Layer 1** rules + S-property | exhaustive proof is cheap here |
| "…must have a Y before…", "after Z it is frozen" | **Layer 1** deny + lifecycle + `only_into` | state discipline is rule territory |
| "…even while the migration runs", "two requests at once", "the job retries" | **Layer 2** model, then conformance | only interleavings expose it |
| "eventually", "within/by <time>", ordering across requests | **Layer 2** (temporal props under fairness) | Layer 1 sees one situation at a time |
| "the UI should…", "make it feel…" | **free layer**, agent-built under the **Layer 3** gate | no policy content |
| "sum/count of…", fuzzy matching, ranking | projection at the boundary, or deliberately client-side — *written down* | outside the finite vocabulary |

Two composition invariants sit under the table. **Anything that guards
must sit below the seam it guards** (context joins in the kernel, not
the client; money truth from the bank feed, not the UI). **Anything
excluded is excluded by written decision** — keep a register of
exclusions with the reason and the designed remedy; Part 5 is that
register for the system itself.

### 4.2 One vocabulary, end to end

The same identifier — `no_self_decision`, `sealed_thread`,
`org_walls` — appears in the ticket, the rule, the S-property, the
feature step's `denied_by:`, the analyzer finding, the kernel's
`Denied.rule.id`, the HTTP 403 body, and the UI toast. This is not
cosmetic. It is what makes the system *debuggable across layers*: a
support engineer pastes a 403 name and lands on the product sentence
and the proof that guards it; an agent's counterexample names the same
atom the product owner approved. Guard the vocabulary the way you
guard the gate: one name per concept, no synonyms, no renames without
a migration of every artifact.

### 4.3 Every seam has a mechanical check

The system's honesty lives at its seams — each one held by a machine,
never by convention:

| Seam | Held by |
|---|---|
| rules ↔ runtime | exhaustive two-backend agreement (runtime eval vs Z3, all situations) |
| kernel ↔ UI | boundary lint in CI + a preserved bypass variant that must FAIL |
| model ↔ code | conformance harness driving the real system (Layer 2) |
| spec ↔ agents | the frozen region diffed and reverted mechanically (Layer 3) |
| NL ticket ↔ formal rule | the one unsound seam — held by grounded human review + the gate's redundancy (see 4.6) |

When you extend the system, this is the design question to ask first:
*what mechanically holds the new seam?* If the answer is "discipline",
the seam is already leaking.

### 4.4 One ticket, end to end

The composition is best shown on one ticket crossing every layer:
**"rename a column on a live table — zero downtime, no stale reads."**
This is the chain Parts 2 and 3 walked in pieces; here it is whole.

**Routing.** Per 4.1: the *tenancy and policy* of the data stays Layer
1 (the org-wall rules don't change and stay proven through the
migration — nothing about renaming a column may touch them). The
*choreography* — backfill racing writes, two app versions live at
once — is interleaving-shaped: Layer 2. The *code* — protocol fixes,
the backfill implementation — is agent work: Layer 3.

**Layer 2, design.** The expand/contract choreography becomes a
270-line model with three one-liner invariants. The checker falsifies
two successive designs a careful engineer would have shipped — each
fix annotated in the model where it lives.

**Layer 2, code.** The conformance harness runs the real API ×2
versions against a real database under the same invariants (same
vocabulary, line-for-line correspondence) and catches a TOCTOU race in
the modern instance that no model predicted — plus the permanent
negative test: skip the drain, get the anomaly, proving the model's
precondition load-bearing in production code.

**Layer 3.** The falsified design's second bug becomes the repair
task. A safety-only gate accepts a partial fix that trades away
completion — and that counterexample becomes two frozen feature runs
plus a completion witness (the ratchet, 4.5). The strengthened gate
forces the full fix from the same model and prompt in one round.

**Escalation.** The repaired protocol then climbs the ladder:
inductive invariant (safety at every depth), EPR (any number of keys
and instances — where the negative control also certifies the original
bug admits *no* inductive invariant at all), liveness (completion
needs only deploy fairness).

The counterexample flow, layer to layer:

```
 falsified design #2 (L2 model trace)
   → repair task (L3)
     → partial fix exposes the gate gap (safety-only)
       → gap becomes frozen feature runs + witness (gate ratchet)
         → full fix, one round, generic prompt
           → proofs: inductive → parameterized → liveness (L2 ladder)
```

One ghost variable (`lastReadOk`) carries the correctness story from
the first model trace to the conformance assertion to the frozen
repair gate. That continuity — not any single layer — is the system.

### 4.5 Incidents: the ratchet

A production bug in this system has a fixed afterlife: reproduce it as
a counterexample *in gate vocabulary* (a feature step with a
`denied_by`, an S-property, a model trace, a conformance divergence);
add it to the frozen gate; only then repair — usually by pointing an
agent at the failing gate. The gate only ever tightens. Clearance's
first draft failing forever in its check, the no-drain anomaly
reproduced on demand by the conformance harness, the stale-row
recovery run frozen into the repair gate — same ratchet, three layers.

### 4.6 What stays human

The system removes diff review, not judgment. Humans still own: the
**tickets** (what should be true); **spec review** — reading rules and
gate sentences against ticket English, sentence by sentence, because
NL→formal translation is the one unsound step and the solver cannot
know what you *meant*; **vocabulary admission** (every new fact is an
ontology commitment); **gate weakening** (agents may propose, never
apply); and **the layer-routing calls** of 4.1. Notice these are all
spec-side acts. That is the job now: you are the author and reviewer
of *meaning*; the machines own *conformance*.

### 4.7 Starting tomorrow (adoption path)

You do not adopt three layers in one quarter. The order that works:

1. **Gate an existing service's riskiest surface** (authz) with Layer
   1: extract the decision into a rule base, run the analyzer, keep
   your existing code as the enforcement point *temporarily*, checked
   by two-backend agreement.
2. **Move enforcement into the kernel** service by service; add the
   boundary lint; let the UI go free.
3. **Introduce the Layer 3 gate on one repo** — freeze the rule base +
   gate files, let an agent take tickets, review only findings.
4. **Reach for Layer 2 the first time a design has a migration or a
   job in it** — one model, one falsified design, and the team will
   not need convincing again.

---

## Part 5 — Costs, limits, and when not to use it

Nothing in this part is aspirational or defensive boilerplate: these
are the system's actual characteristics as they stand, priced. A limit
you cannot state is a limit you will rediscover in production.

### 5.1 The bill, itemized

**What an application costs.** Per-domain YAML stays flat at roughly
150 lines *per entity* (the shipped examples range from 65 to 160
lines of rules for single-entity services; a three-entity helpdesk is
278 — the "flat" claim is per entity, not per service). A complete
kanban SaaS is about an hour of author time from tickets to green
gate, almost all of it *writing* the two YAML files, effectively none
of it debugging.

**What the platform costs.** The generic engine + analyzer is ~2,300
domain-free lines, amortized over every application you run on it.
Each new domain costs at most **one missing generic concept** — the
engine has grown time (date projections, a clock), actor↔resource
relations (tenancy, assignment), and child entities this way, roughly
100 lines each — and the curve converges: recent domains have cost
zero engine lines.

**What checking costs.** Analyzer rounds: ~0.2 s single-entity, ~0.4 s
for three entities — review latency is effectively zero. The exhaustive
runtime↔solver agreement is the expensive rung: ~80–85 s in CI for a
25–35k-situation service, and exponential in projections — the
vocabulary budget is also a CI budget.

**What the gate pays back.** On the kanban example alone, the
∀-checks caught two real authorization holes before any code ran — a
task assigned to `anonymous` handing work to the public, and a broad
staff allow quietly granting the team's work. Both are *interaction*
bugs: each rule reads fine alone, and nobody writes the test where a
task is assigned to "anonymous". The dead-rule check additionally
proved a containment deny load-bearing, then proved it dead after a
fix — it is a live diagnostic of your containment regime.

### 5.2 The sharp edges

The known frictions, consolidated. "Closed" means an engine change
removed it; "open" means you will hit it.

| Sharp edge | Status |
|---|---|
| Projections read like actor facts but live under `resource.*` (`assigned_to_me`) — fails loud at load | open (naming convention) |
| `denied_by` names are declaration-order among overlapping denies — place probes in the minimal state that triggers them | open (an analyzer check is designed) |
| Edits were blind to proposed values — vocabulary gaps fail loud, *semantic* gaps fail silent | **closed** by two-phase edits (15 lines) |
| Assumptions are trusted axioms, not proven — a stale one is silent unsoundness | partially closed: creating-roles-must-be-assumable-authors is checked; the rest is open |
| `default_deny` flattens refusal UX exactly where the rule base is leanest (containments have no rule to name) | open (nearest-allow explanations are solver-computable but unbuilt — and an explanation is a disclosure channel, so tenancy walls apply to error messages too) |
| The Python boundary lint is a lint plus name-mangling, not a proof — it guarantees the bypass cannot happen *quietly* | open (the by-construction version is a process boundary, or a compiler — see 3.6) |
| Two decisions per edit ≠ transactionality: a concurrent writer between decide and write is Layer-2 territory | open |
| Untagged global denies fail OPEN for child entities | fixed in the shipped examples and pinned both directions; a load-time lint is designed |
| Parent-delete cascades skip child delete rules — and the per-entity gate *cannot see it* | open, pinned by an engine test |
| No aggregates over children; one nesting level; one parent per child | open by design — an aggregate atom is not a free boolean for the analyzer (it couples the parent's space to the child rules: a frame problem); the designed cut is kernel-computed aggregate projections, runtime-sound and analyzer-conservative |
| Field-level visibility: a redacted comment is a readable row whose body the UI *chooses* to tombstone | open — honestly outside the verified boundary today |
| Child `visible()` is N+1-shaped under load | open |
| The engine clock is a trust root (`is_past_due` is only as true as the server's date) | open |

One meta-edge worth more than the table: **a clean first run is
evidence that the discipline transferred, not that the gate is
redundant.** The same author who writes a round-1-green rule base
today produced two real authorization holes one domain earlier. The
gate stays frozen precisely for the author who has not yet been bitten.

### 5.3 How limits stay honest

Every limit above is written down with the condition that would force
it and the designed remedy — aggregates get kernel-computed
projections when a ticket demands them, the cascade gets
cascade-decides or a load-time compatibility check, the N+1 join folds
into a reporting seam that applies the read rule per row at SQL speed.
Treat your own exclusions the same way: a register of what the system
deliberately does not do, each entry carrying its trigger and its
remedy, reviewed when tickets approach it. Limits managed this way get
scheduled; limits managed by folklore get discovered.

### 5.4 When not to use this

- **Rules don't compute.** Rendering, search, diffing, billing
  arithmetic, migrations are code. The claim is that *domain policy*
  is rules — which, for a CRUD SaaS, is where most ticket-driven
  change lands, but it is not everything.
- **The scope is ordinary web software** — CRUD/API, authz, tenancy,
  workflow. The assurance ceiling of Layer 1 is exhaustive finite
  checking; if your risk profile needs verified compilers and
  proof-carrying code, this is not that.
- **The reference engine is unproven Python.** Sound for everything
  the analyzer checks (the runtime and the solver agree exhaustively),
  but the engine itself is trusted. A hardened deployment rests trust
  on a formally verified policy engine plus the same per-change
  analysis.
- **Cross-item and relational invariants** ("≤3 published per
  author", dedup/idempotency) are outside the situation vocabulary —
  store constraints and Layer-2 models are the escalation path.
- **Untested fits**: a tiny single-role CRUD app may not repay the
  gate-writing; hard real-time and ML-shaped logic (ranking,
  moderation) have no obvious rule-shaped core. Judge these yourself —
  the system has nothing to say about them yet.

### 5.5 Alternatives considered

Design decisions you would otherwise re-litigate:

- **Exhaustive enumeration vs. bounded model checking of the decision
  kernel.** At finite domains (a 64-point decision space, or 3,456
  situations), exhaustive enumeration matches model-checking-grade
  assurance at zero setup cost and sub-second runtime. Symbolic tools
  (e.g. Kani for Rust) win the moment unbounded types — ids, strings —
  enter the kernel's signature: they prove in ~0.1 s what enumeration
  could never finish. The system uses enumeration today because its
  decision vocabulary is finite by construction; the crossover is
  known and priced.
- **Alloy for rule analysis** — declined: Z3 already covers
  single-state analysis; Alloy would add instance visualization only.
- **Generating implementation code from the temporal model** —
  declined: no mature toolchain exists; the conformance harness holds
  the seam instead.

---

## Appendix A — Commands

```bash
# the analyzer (the type-checker of this system) — from the engine dir:
python -m analysis.analyze <ruleset-dir>              # gate of that dir
python -m analysis.analyze <draft-dir> --gate <frozen-ruleset-dir>
python -m analysis.boundary <app-dir>                 # kernel-only imports
python live_demo.py <ruleset-dir>                     # features over HTTP

# the modeling toolchain (off the shelf):
quint run model.qnt --main <cfg> --invariant invAll   # random simulation
quint verify model.qnt --main <cfg> --invariant invAll --max-steps 12
quint test model.qnt --main <cfg>                     # scripted runs
quint run model.qnt --mbt --out-itf trace.itf.json    # model-based testing

# shipped examples, one command each:
examples/approvals/check.sh     # Clearance — this manual's worked example
examples/helpdesk/check.sh      # the multi-entity helpdesk with the free UI
examples/taskboard/check.sh     # the kanban SaaS
```

## Appendix B — File layout of a Layer-1 application

```
<service>/
  TICKETS.md                      # product English, quantifiers intact
  rulesets/<service>/
    rules.yaml                    # THE PROGRAM: vocabulary + rules
    safety.yaml                   # FROZEN gate: S-props, witnesses, only_into
    features.yaml                 # FROZEN gate: scenarios, denials by name
  rulesets/<service>-round1/      # preserved buggy drafts the gate must fail
  app.py                          # FREE layer: hand-written UI, kernel-only
  tests/                          # incl. exhaustive two-backend agreement
  check.sh                        # one command: gate, negatives, HTTP replay
```

## Appendix C — Glossary

- **situation** — one point of the finite decision space: (role,
  active, is_author, action, state, has_*, projections, parent.*).
- **projection** — a named boolean distilled from live data at the
  boundary (`same_org`), so rules stay propositional.
- **gate** — the frozen acceptance surface: safety ∀ + possibility ∃ +
  lifecycle jurisdiction + feature runs. Both directions, always.
- **witness** — a concrete situation proving an ∃-property, with the
  granting rule named.
- **dead rule** — a rule that never changes any decision; a finding.
- **containment** — a role's proven blast radius (tight allows +
  S-property, no deny).
- **kernel** — the sole enforcement point; app code imports it and
  nothing beneath it.
- **frozen region** — spec files agents cannot edit; enforced by diff
  + revert, not convention.
- **ghost variable** — model state the real system doesn't have,
  tracked purely so correctness is statable (`lastReadOk`).
- **counterexample** — machine-readable refutation (analyzer finding,
  ITF trace, conformance divergence); the currency all layers trade in.
