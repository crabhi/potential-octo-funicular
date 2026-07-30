# The workflow, holistically: a novel way to develop large-scale systems

Date: 2026-07-30. Status: draft (written for the M3 review + slide deck).

## Thesis

When LLM agents write most of the code, the scarce resource is no longer
implementation effort — it is **trustworthy intent transfer**. Tests sample
behavior; reviews sample attention; neither scales with agent throughput.
The proposal: make the developer's intent a *formal, machine-checkable
artifact*, and make every agent edit pass through reasoning engines that
hold the implementation to it. The spec becomes the durable asset; code
becomes a regenerable projection of it.

This inverts the traditional economics: formal methods used to be too
expensive because specs were written *in addition to* code by the same
scarce humans. With LLMs, (a) translation NL→formal is assisted and cheap
to iterate, (b) the checker's counterexamples are consumed by an agent that
never tires, and (c) the payoff of one spec is amortized over unbounded
agent regenerations of the code.

## Roles

- **Developer** — authority over intent. States invariants in NL, reviews
  their formal translation (grounded sentence-by-sentence, never raw logic
  as the primary view), owns every spec change. Never needs to babysit
  individual code edits.
- **LLM agents** — translation (NL→formal, checker-in-the-loop) and
  implementation/optimization (edit code freely *within* the frozen spec).
  Weaker/cheaper models do the mechanical fan-out; the spec gate makes
  their output trustworthy anyway — the gate, not the model, carries the
  correctness burden.
- **Reasoning engines** — arbiters. SMT solver for the static invariant
  layer (contradictions, vacuity, claim verdicts), model checker for the
  temporal/concurrency design, conformance harness + (later) history
  checkers for the running system. Sound where it matters; the unsound
  LLM translation step is always followed by a sound validation step
  (the AWS translate/validate split, note 06).

## The contract that makes autonomy safe

1. **The spec is frozen for the agent.** Code edits cannot weaken the gate;
   spec edits are a human ceremony. This is the load-bearing rule — without
   it the agent optimizes the gate instead of the code.
2. **Counterexamples are the universal currency.** Solver cores, checker
   traces (ITF JSON), failing generated tests — all normalized into one
   "violated invariant + concrete scenario + prior attempt" payload that
   flows back to whichever agent proposed the change (CEGIS shape, note 06).
3. **Green must be meaningful.** Prefer oracles with crisp completeness
   stories (model-checked bounds, unsat cores, anomaly-complete history
   checking) over "N random runs found nothing"; layer them (design model →
   generated tests → history checks → selective code proofs) so the gaps of
   one layer are covered by another (D4, note 02).
4. **Objective functions live outside the gate.** Performance, cost, latency
   are optimized only within the feasible region the spec defines. The agent
   may make the system faster in any way it likes; it may not make it wrong.

## Why the DB-migration case study is the right hard case

Online schema change concurrent with traffic is (a) ubiquitous at scale,
(b) formally treated exactly once in the literature (F1, note 05) while
every OSS tool ships informal correctness stories, and (c) small enough to
model completely. Our own M3 evidence shows the leverage: the checker
falsified two successive protocol versions a careful engineer believed
correct (P1 README), the same invariant was then shown empirically
load-bearing against a real Postgres system (P3, 59 anomalies per run when
the drain precondition is deliberately skipped), and a genuine TOCTOU race
was found in the "modern" instance itself — the class of bug that survives
code review and unit tests, and precisely what an autonomous optimizing
agent must be fenced against.

## What is novel here (vs. existing art)

- **No mainstream agent product gates edits on a formal checker** (note 06:
  SpecKit et al. are prose-spec tools). The gap between "LLM+verifier
  research loops" (Dafny/Verus benchmarks) and "agent workflow products" is
  exactly where this project sits.
- **The two-layer spec** (typed reviewable invariants compiled into a
  temporal model) combines the only two things that are known to work:
  restricted rule languages for reliable LLM translation + human review
  (Bedrock AR), and TLA-family models for concurrency reasoning.
- **Formalizing online migration choreography** for app-level dual-writes
  (drain scope, IS-DISTINCT-FROM backfill) appears to be genuinely new —
  the OSS tools never published correctness arguments, and P1's two
  counterexamples are not in the literature we surveyed.
- **Spec-as-fence for optimization** (agent maximizes an objective inside a
  frozen formal feasible region) rather than spec-as-target for synthesis —
  most verified-codegen work aims at "generate correct code once", not
  "keep an autonomously evolving system inside the envelope".

## Adoption path for a real team (ease-of-use view)

1. Start with P2-style typed invariants on one subsystem — zero new
   languages for the team; review stays in NL + examples.
2. Add the design model only where concurrency actually bites (migrations,
   caches, queues); agents write the Quint, humans read counterexamples,
   not specs.
3. Bind the spec to reality via generated tests first (cheap, MongoDB
   lesson), history checking second, proofs last and selectively.
4. Only then let agents optimize autonomously, gated by all of the above.
   Each stage pays for itself before the next is needed.

## Open research questions

- NL→spec fidelity at scale: when does the two-layer split stop being
  enough and full temporal specs need direct LLM authoring?
- Trace-first specs: can we design specs so conformance instrumentation is
  generated, not retrofitted (TraceLink direction)?
- Spec review UX: what does the "fidelity report" look like for temporal
  properties, where witnesses are traces rather than single states?
- Composition: whole systems need many small specs — what is the module
  system / refinement discipline that keeps checking tractable?
