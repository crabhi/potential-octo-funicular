# Spec languages & model checkers

Date: 2026-07-30. Status: draft.

## TL;DR

- **TLA+ (TLC/Apalache/PlusCal)** is the safest default: huge training-data
  footprint, explicit refinement mapping support (serializable -> concurrent
  is a first-class use case), machine-readable JSON traces, and a documented
  case study of exactly our scenario (zero-downtime DB migration + concurrent
  requests, in PlusCal).
- LLMs write **syntactically valid** TLA+/Quint almost every time, but
  **semantic fidelity to a real system collapses** (~16-81% on invariant
  checks per SysMoBench, 2026) unless the agent is given tool feedback loops
  and reads real code/traces — plan for iterate-on-counterexample as core
  workflow, not one-shot generation.
- **Quint** is TLA-semantics with a friendlier, TypeScript-like syntax, a
  real CLI/LSP, and (as of 2025-2026) an official **LLM Kit** with
  Claude Code agents purpose-built for spec generation/repair — worth
  prototyping first given the out-of-the-box LLM tooling.
- **P (Microsoft)** is the best fit if we want to model actual
  request-handling code as communicating state machines and get both model
  checking and systematic testing of the real implementation; it already has
  production use at AWS and an emerging MCP/AI-agent tool ecosystem.
- **Alloy 6, Ivy/mypyvy, Stateright, FizzBee** are all real options but each
  has a gap for us: Alloy is relational/bounded and less LLM-common; Ivy/
  mypyvy target first-order-logic protocol proofs with a steep learning curve
  and small training corpus; Stateright requires writing Rust and hand-rolled
  linearizability checks; FizzBee is young but notably Python/Starlark-based,
  which is likely the most LLM-native syntax of the bunch.
- No tool does step 3 of the pipeline (querying an invariant set for internal
  contradictions before code exists) as a first-class feature — that's
  closest to what TLC/Apalache/Quint's simulator + "vacuity"/"trivial
  invariant" checks give you, but it will need custom scaffolding regardless
  of language choice.

## Inventory

| Tool | What it is | Maturity | License | LLM-friendliness | Machine-readable output? |
|---|---|---|---|---|---|
| TLA+ / TLC | State-based temporal spec language + explicit-state model checker | Very mature (1999-, Lamport); huge corpus, industrial use (AWS, MS, MongoDB) | MIT (tlaplus/tlaplus) | High — most training data of any tool here | Yes: `-dumpTrace json` gives JSON error traces; also `.tla`/`.out` |
| Apalache | Symbolic (SMT-based) model checker for TLA+, bounded + some unbounded checks, type checker | Mature, active (informalsystems/apalache-mc, CAV papers) | Apache-2.0 | High (same spec language as TLA+) | Yes: `counterexample.json`, `counterexample.tla`, `MC.out`; structured type-check errors |
| PlusCal | Algorithm-like DSL that transpiles to TLA+ | Mature, bundled with TLA+ tools | MIT | High — reads like pseudocode/imperative code, easiest on-ramp for LLMs | Inherits TLC/Apalache output |
| Quint | TLA-semantics spec language, TS-like syntax, own simulator + Apalache backend | Maturing fast; stable CLI/VS Code ext; spinning out as its own company (Apr 2026) | Apache-2.0 | High and rising — has an official **Quint LLM Kit** (Claude Code agents) and "Quint Connect" model-based-testing lib | Yes — Apalache backend output + Quint's own itf.json trace format (Informal Systems' standard trace format) |
| Alloy 6 / Electrum | Relational first-order logic + linear temporal logic, SAT/SMV-backed bounded & unbounded model checker | Mature core (Alloy since 2000s), Alloy 6 (temporal, ex-Electrum) since ~2022 | MIT | Medium — well-known academically, less represented than TLA+ in code-generation corpora | Partial — Analyzer UI-first; Electrum/Electrod CLI exists but structured output is less standardized |
| P (Microsoft) | Compiled DSL: model system as communicating state machines; supports model checking + systematic/random testing of compiled code | Mature & production-used (AWS S3/EBS/DynamoDB, MS), active releases (2.3.5, Feb 2025) | MIT | Medium-high, improving fast — new MCP server w/ 27 tools, RAG examples, Cursor/Claude Code integration | Yes — PChecker emits structured bug traces/logs; compiles to C#/C/Java for CI |
| Ivy | Interactive, multi-modal (decidable FOL fragment) verification tool for distributed protocols | Mature but niche/academic | BSD-ish (open) | Low — small corpus, steep FOL/EPR modeling discipline | Limited — proof obligations & CEX are FOL-logic artifacts, not friendly JSON |
| mypyvy | Research platform, similar to Ivy, FOL transition systems + automated invariant inference (PDR∀) | Active research tool (CAV'24), not intended as a "product" | Open (MIT-ish) | Low — very small training footprint, aimed at verification researchers | Text/log output, no stable JSON schema found |
| Stateright | Rust library: model + explicit-state checker + actor runtime + linearizability tester | Actively maintained (commits through mid-2025) | MIT/Apache-2.0 dual (typical Rust) | Medium-high — it's just Rust code, so any Rust-capable LLM can write models; no separate DSL to learn | Yes-ish — Rust `Debug`/structured counterexample via its `Checker` trait; no fixed external schema, but easy to serialize since it's your own Rust |
| FizzBee | Python/Starlark-syntax spec language + BFS model checker (Go-implemented), supports probabilistic + actor/OO/functional styles | Young (design partner era, ~2023-), active releases through 2026, has a hosted playground | Apache-2.0 (fizzbee-io) | High for syntax (looks like Python), low for training-data volume (new language) | Partial — CLI + playground; JSON/trace tooling exists but less mature/standardized than TLA+ ecosystem |
| (Notable others) TLAPS, Dafny/F*/Lean, Spin/Promela | Proof assistants / code-level verification (step 4 of pipeline) and classic model checkers | Mature | Various OSS | Varies (Dafny/Lean well-represented; Promela less so) | See per-tool notes below |

## Per-tool assessment

### TLA+ (TLC + Apalache + PlusCal)
**Strengths for this project**: Concurrency and refinement are exactly what
TLA+ was built for — Lamport's own material walks through refinement mappings
from an abstract (serializable) spec down to a concurrent implementation,
which maps directly onto our "start serializable, extend to concurrency"
plan. There is a public worked example of a zero-downtime DB migration
running concurrently with client requests in PlusCal, checked against a
`ConsistentViews`-style invariant by comparing a "with migration" and
"without migration" model — structurally very close to what we need
(migrations + concurrent API requests + an invariant). TLC's `-dumpTrace
json` and Apalache's `counterexample.json` give a real machine-readable
counterexample an agent can parse and act on.
**Weaknesses**: TLC's explicit-state search explodes with concurrency +
data-heavy state (our "requests + DB rows" domain will have large state
spaces) — will likely need Apalache (symbolic/bounded) or aggressive state
abstraction. LLM benchmarks (SysMoBench, mid-2026) show that while models
write valid-looking TLA+ near 100% of the time, actually matching a real
system's transitions is the hard part (41-46% average); expect to need an
agentic loop that reads real code/traces, not pure NL-to-spec generation.

### Quint
**Strengths**: Same TLA semantics as above (so refinement path is inherited)
but a far friendlier concrete syntax (types, modules, `run`/`test` blocks),
a real CLI + VS Code extension, and — notably — an official **LLM Kit**
(Claude Code agents + validation loop) shipped by the maintainers
specifically to close the "LLM writes plausible-but-wrong spec" gap.
Backed by Apalache, so we keep the symbolic checker's counterexample
quality. "Quint Connect" (Dec 2025) targets model-based testing in Rust,
which is directly relevant if the implementation language ends up Rust.
**Weaknesses**: Newer language, smaller pretraining footprint than raw
TLA+ (mitigated by the LLM Kit's few-shot scaffolding); the company is
mid-spinout (Apr 2026) — some tooling/roadmap risk in the next 12 months.

### Alloy 6 (Electrum)
**Strengths**: Very strong for *structural* invariants over relations
(e.g., "every request maps to at most one row version", schema-shape
constraints during migration) and Alloy's counterexample visualizer is
excellent for a human reviewing model output. Alloy 6 added genuine LTL-style
temporal operators, so migrations-as-mutable-state are expressible.
**Weaknesses**: Bounded model checking by default (SAT-based); unbounded
mode via Electrod/NuSMV is available but less turnkey. Much less
represented in LLM training corpora than TLA+; tooling is UI-centric
(Analyzer app) rather than CLI/CI-first, though a Java API and Electrum CLI
exist. Refinement between two Alloy models is possible but far less
documented/idiomatic than TLA+'s refinement-mapping culture.

### P (Microsoft)
**Strengths**: Unique in this list for closing the loop to real code — P
models compile to executable state machines (C#/C/Java) that can be
systematically/randomly tested, so the same artifact used for model checking
can drive test generation against the actual implementation (relevant to
pipeline step 4, "verify actual system behavior"). Proven at industrial scale
on exactly this class of problem (S3 consistency migration, DynamoDB,
storage systems with online changes + concurrent traffic). 2025-2026 saw a
purpose-built MCP server (27 tools) plus RAG examples and an auto-fix
pipeline for AI-assisted P authoring — most mature "LLM writes formal spec
and iterates" tooling outside of Quint's LLM Kit.
**Weaknesses**: State-machine/message-passing modeling style is a bigger
conceptual jump than "write an action/transition relation" (TLA+/Quint) if
our natural framing is "requests + DB migration as shared mutable state"
rather than actors exchanging events — modeling API requests as
messages-to-a-DB-actor is doable but adds translation overhead. Community/
training-data footprint is smaller than TLA+.

### Ivy / mypyvy
**Strengths**: If we eventually need *unbounded* (all state spaces, not just
bounded-depth) safety proofs of an inductive invariant — e.g., proving a
locking/versioning protocol correct for arbitrarily many concurrent requests
— these are the right academic-grade tools, and mypyvy's PDR∀ can help
*infer* the inductive invariant rather than requiring the developer to hand
supply it.
**Weaknesses**: Both require modeling in a decidable fragment of first-order
logic (EPR) — a real discipline that's hard even for experienced formal
methods people, let alone an LLM. Tiny training corpus (research tool,
not much public code), no stable JSON output, no LSP/CI-first tooling.
Best treated as a possible *later* escalation path for a narrow, critical
sub-protocol, not the main modeling language.

### Stateright (Rust)
**Strengths**: No new DSL — invariants and transition systems are written
as plain Rust, which plays extremely well with "implementation languages:
Python, Rust, Java, Go" and with LLMs' general Rust fluency (much larger
corpus than any spec-DSL). It ships an actor runtime and a linearizability
checker explicitly aimed at "is this concurrent implementation correct
w.r.t. a sequential spec" — almost exactly our serializable-to-concurrent
refinement question. Being a library rather than a standalone checker
means it is CI-native by construction (`cargo test`).
**Weaknesses**: Because it's "just Rust", there's less of a firewall between
spec and implementation than a dedicated spec language gives you — easy to
accidentally end up "verifying" a straight copy of the implementation code
rather than an independent, abstract model. No standardized counterexample
schema beyond whatever Rust structs you choose to log/serialize (which is
also an opportunity — it's trivial to make it as machine-readable as we want).

### FizzBee
**Strengths**: Syntax is Python/Starlark, arguably the most LLM-native
input language on this list given the sheer scale of Python in every model's
pretraining data. Supports actor/OO/functional style, probabilistic
modeling, and fairness/liveness checks. Has a hosted playground for cheap
experimentation and a real (small but responsive) community
(surfingcomplexity.blog and others actively writing FizzBee case studies,
e.g. locks/leases/fencing tokens in 2025).
**Weaknesses**: Young project — expect rough edges, smaller ecosystem,
less-battle-tested refinement/composition story than TLA+, and much less
pretraining exposure for the language itself (mitigated by its Python-like
surface syntax, which an LLM can mostly pattern-match even with few
FizzBee-specific examples).

### Notable adjacent tools (not full profiles)
- **TLAPS** — mechanical, Isabelle-backed proofs over TLA+ specs; relevant
  for machine-checked proofs of one critical invariant (pipeline step 4).
- **Dafny / F\* / Lean** — code-level proof languages; relevant to "verify
  actual system behavior" via code-level proofs, a different pipeline step.
- **Spin/Promela** — classic concurrent-systems checker, largely superseded
  by TLA+/P here; lower LLM familiarity than TLA+.
- **SysMoBench / Specula** (2026 research) — not adoptable directly, but its
  agentic-harness pattern ("read the real repo, drive the spec workflow
  autonomously, validate against traces") matches our pipeline step 4 and is
  worth mining for design ideas.

## Fit for the workflow

1. **NL invariants -> formal language (step 2)**: Quint (LLM Kit) or P (MCP
   tools + RAG) currently have the most ready-made LLM-assisted authoring
   tooling. TLA+/PlusCal is the safest fallback given raw model familiarity
   with the syntax even without special tooling.
2. **Contradiction/vacuity check on the invariant set alone (step 3)**: best
   served today by TLC/Apalache's/Quint's simulator (random/symbolic runs
   with no implementation, checking for vacuously-true or unsatisfiable
   invariants) — no tool here has a dedicated "contradiction detector," this
   needs a thin custom layer (e.g., ask Apalache/Quint to find *any* trace
   satisfying the invariants; UNSAT/no-trace signals a contradiction).
3. **Verify actual system behavior (step 4)**: P is the strongest fit if we
   want spec-to-implementation traceability (compiles to real code, drives
   testing); Stateright if implementation is Rust and we want the spec+check
   embedded in the same codebase/CI; TLA+/Apalache/Quint if we're checking a
   model against traces extracted from the real system (conformance testing,
   à la SysMoBench's approach).
4. **Agent optimization under formal constraints (step 5)**: whichever
   language we pick needs a fast, scriptable, non-interactive checker
   invocation with structured output for the optimizing agent to consume as
   a reward/constraint signal — TLC (`-dumpTrace json`), Apalache
   (`counterexample.json`), Quint (itf.json via Apalache backend), and
   Stateright (native Rust, serialize whatever we want) all satisfy this;
   Ivy/mypyvy currently do not.

## Prototype ideas (1-2 day scale)

1. **PlusCal/TLA+ migration-vs-no-migration prototype**: adapt the public
   zero-downtime-migration PlusCal example (two DBs, tombstones, background
   copy process, `ConsistentViews` invariant) to our API-request framing;
   run TLC with `-dumpTrace json`; feed a deliberately-broken variant's
   trace to an LLM agent and see if it can localize + fix the bug from the
   JSON trace alone.
2. **Quint LLM Kit spike**: install `quint-llm-kit`'s Claude Code agent,
   give it 3-5 NL invariants about concurrent requests + a migration flag
   flip, and see how many round-trips to a working spec it needs; compare
   against hand-writing the same spec in raw TLA+ with a generic prompt, as
   a rough LLM-friendliness A/B.
3. **Stateright serializable-refinement check**: write the target system's
   "serializable" reference model in ~50 lines of Rust/Stateright, then a
   second "concurrent" model with a specific primitive (row versioning or a
   migration flag), and use Stateright's linearizability tester to check the
   concurrent model against the serializable one — directly prototypes the
   refinement step called out in the brief.
4. **Contradiction-detection micro-tool**: given a small invariant set in
   Quint or TLA+, script "does any trace satisfy all invariants at once"
   (Apalache `check` with a trivial init, or Quint's `run`); wrap it so an
   agent can call it before any implementation exists, matching pipeline
   step 3.

## Sources

- [Can LLMs model real-world systems in TLA+? – ACM SIGOPS](https://www.sigops.org/2026/can-llms-model-real-world-systems-in-tla/)
- [Can LLMs Write Correct TLA+ Specifications? (arXiv 2606.05792)](https://arxiv.org/pdf/2606.05792)
- [TLA-Prover: Verifiable TLA+ Specification Synthesis (arXiv 2606.06133)](https://arxiv.org/pdf/2606.06133)
- [Apalache — Running the Tool docs](https://apalache-mc.org/docs/apalache/running.html)
- [TLC "save error trace in user-defined formats" (GitHub #640)](https://github.com/tlaplus/tlaplus/issues/640)
- [using:tlc:start — TLA+ Wiki](https://docs.tlapl.us/using:tlc:start)
- [Quint (GitHub, quint-co/quint)](https://github.com/quint-co/quint)
- [Quint LLM Kit (GitHub)](https://github.com/informalsystems/quint-llm-kit)
- [Quint Connect blog post](https://quint.sh/posts/quint_connect)
- [Quint FAQ](https://quint-lang.org/docs/faq)
- [Electrum (GitHub, haslab/Electrum)](https://github.com/haslab/Electrum)
- [Alloy 6 overview — Formal Software Design with Alloy 6](https://haslab.github.io/formal-software-design/overview/index.html)
- [Alloy 6 release page](https://alloytools.org/alloy6.html)
- [P (programming language), GitHub p-org/P](https://github.com/p-org/P/)
- [What is P? — p-org.github.io](https://p-org.github.io/P/whatisP/)
- [mypyvy CAV'24 paper (PDF)](https://www.wisdom.weizmann.ac.il/~padon/mypyvy-cav2024.pdf)
- [Ivy — safety verification by interactive generalization](https://www.researchgate.net/publication/305793322_Ivy_safety_verification_by_interactive_generalization)
- [Stateright (GitHub, stateright/stateright)](https://github.com/stateright/stateright)
- [Model Checking: Use Stateright to Formally Verify Raft Lite](https://liangrunda.com/posts/raft-lite-model-check/)
- [FizzBee (GitHub org, fizzbee-io)](https://github.com/fizzbee-io)
- [FizzBee quick start](https://fizzbee.io/design/tutorials/quick-start/)
- [Locks, leases, fencing tokens, FizzBee! – Surfing Complexity](https://surfingcomplexity.blog/2025/03/03/locks-leases-fencing-tokens-fizzbee/)
- [Zero-downtime database migration in PlusCal (worked example)](https://biradarganesh25.github.io/pluscal/db_migration.html)
- [Specifying serializability in TLA+ – Surfing Complexity](https://surfingcomplexity.blog/2024/10/28/serializability-and-tla/)
- [Linearizability! Refinement! Prophecy! – Surfing Complexity](https://surfingcomplexity.blog/2024/09/22/linearizability-refinement-prophecy/)
- [Software is infrastructure (arXiv 2506.13821)](https://arxiv.org/pdf/2506.13821)

## Open questions

- Do we need *unbounded* proofs (Ivy/mypyvy/TLAPS-grade) for any single
  invariant, or is bounded/symbolic model checking (TLC/Apalache/Quint/
  FizzBee) sufficient given we control the deployed state-space size?
- How much of "the real system" should the model read directly (agentic,
  SysMoBench-style conformance) versus staying a hand-authored abstraction
  the developer reviews? This changes whether Quint's LLM Kit or P's MCP
  server is the better fit.
- Is the target implementation language actually going to be Rust? If yes,
  Stateright's "no separate DSL" property becomes much more attractive; if
  Python/Java/Go, a standalone spec language (TLA+/Quint/P) more clearly
  earns its translation overhead.
- What does "query for contradictions before any code exists" need to
  produce for the developer — NL explanation, counterexample trace, or
  both? Affects whether we need a post-processing layer on top of
  TLC/Apalache/Quint output regardless of which language wins.
- Should we budget evaluating the same 3-5 invariants across two finalist
  languages (likely TLA+/Quint vs P) before committing, given SysMoBench
  suggests tool + agent scaffolding matters more than raw language choice?
