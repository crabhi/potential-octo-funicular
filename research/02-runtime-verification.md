# Runtime verification & trace checking

Date: 2026-07-30. Status: draft.

## TL;DR

- Two families matter for our workflow: **trace validation against a formal
  spec** (log the running system, replay against TLA+/P and ask "is this a
  legal behavior?") and **model-based / property-based testing** (generate
  request sequences from a model and check invariants as an oracle, ideally
  driving the real API). Both give binary pass/fail signals an agent can
  optimize against; neither *proves* anything — they only fail to find bugs.
- Trace validation is the most direct match for "verify the actual running
  system against a formal spec" but every public account (MongoDB, TLA+ 2024
  papers) reports it is **effort-heavy and spec/impl alignment is the hard
  part**, not the checking mechanics. Retrofitting it onto a spec not written
  with trace-checking in mind mostly fails (MongoDB's own experience: zero
  bugs found, 10+ weeks spent, root cause was spec/impl abstraction mismatch).
- For **concurrent DB access**, the mature, battle-tested tools are Jepsen +
  Elle (transactional consistency anomalies, black-box, JVM-native) and
  Porcupine (linearizability, Go, used by etcd/TiDB/AWS MemoryDB). Both need a
  recorded history (op, start/end time or process order, args, result) — this
  is exactly the shape of API request/response logs we'd already have.
- **Model-based/property-based testing** (Hypothesis stateful testing +
  Schemathesis for OpenAPI, jqwik/quickcheck-state-machine elsewhere) is the
  cheapest to bootstrap for a web API: it needs a model with pre/postconditions,
  not a full temporal-logic spec, and directly drives HTTP calls concurrently.
  It's a good near-term win independent of the TLA+ track.
- **Deterministic simulation testing** (FoundationDB-style, Antithesis,
  madsim/turmoil in Rust) is the heaviest-weight but strongest option for the
  "migrations running concurrently with requests" scenario, because it can
  literally interleave a migration step with concurrent requests under a
  controlled scheduler and replay a failing seed byte-for-byte. Antithesis
  works at the hypervisor level (any language) but is a paid platform and a
  "resource-intensive undertaking" per their own docs; madsim/turmoil are
  DIY, Rust-only, in-language.
- Runtime monitors compiled from LTL/temporal specs (P's monitor machines /
  AWS's PObserve, Reelay, LoomRV) are the right conceptual bridge from
  "invariants as formulas" to "pass/fail on production traffic," and P's
  monitor machines are the most directly reusable idea for our M4 loop since
  they're designed to sit alongside a spec that also model-checks.

## Inventory

| Tool/technique | What it checks | Spec language | Effort to adopt | Concurrent + migration traffic? |
|---|---|---|---|---|
| TLA+ trace validation (Pressler; TLC's `TRACE` feature; Kuppe/Merz 2024 framework) | Is a logged execution a legal behavior of a TLA+ spec | TLA+ (existing spec, reused) | High — needs instrumentation to emit spec-variable deltas + careful abstraction alignment | Yes in principle (spec can model concurrency); migrations would be another action in the same spec |
| MongoDB conformance checking / eXtreme Modelling (test-case gen + trace-checking) | Same as above, plus generating tests from spec | TLA+ / PlusCal, small per-aspect specs | High for trace-checking (MongoDB spent 10+ wks, 0 bugs found); Medium for test-*generation* (2 wks, found a real bug) | Yes — designed for replica-set concurrency; migration-style state changes are just more actions |
| TraceLink (PGo, 2025) | Validates Go implementation traces (generated from PlusCal) against the PlusCal spec via vector-clock-ordered replay | PlusCal → generated Go | Medium, but tied to PGo-generated code specifically | Yes, that's its whole point (concurrent Go processes) |
| Jepsen + Elle | Transactional consistency anomalies (G0/G1/G2, write cycles, read skew, anti-dependency cycles, dirty/duplicate writes) | No temporal spec — a fixed catalogue of consistency models (`consistency_model.clj`); you pick the target model (e.g. snapshot isolation) | Medium — need a recorded history (Jepsen format) of your API's DB-touching ops incl. concurrency; Elle itself is a Clojure/JVM library, usable standalone | Yes, this is its core use case; nemesis can inject faults but migrations aren't a first-class Jepsen concept — would model migration as another client/process |
| Porcupine (Go) | Linearizability of a concurrent history against a sequential model you write in Go | Go code (executable sequential spec), not a logic language | Low-Medium — write a small sequential model of the operations, feed it a history of (op, start, end, args, result) | Checks linearizability specifically; doesn't model migrations, but you could add a migration "operation" to the sequential model |
| P monitor/spec machines + PObserve (AWS) | Safety/liveness properties expressed as observer state machines, checked against a structured event log, works in test AND production | P language (state machines + assertions) | Medium-High — need the P spec already, then structured logging of the same events | Yes — P specs already model concurrent state machines; production log validation is asynchronous/post-hoc |
| Runtime monitors from LTL/MTL (Reelay, LoomRV, faRM-LTL) | Compiles temporal-logic formulas into streaming monitors that flag violations online | LTL / MTL / STL | Medium — need to translate invariants to temporal formulas and wire monitor inputs to an event stream | Concurrency handled if the event stream totally/partially orders correctly; no native migration concept |
| Hypothesis stateful testing (`RuleBasedStateMachine`) | Runs generated sequences of "rules" (API calls) against a model, checks invariants/postconditions after each step; shrinks failing sequences | Python code (rules + invariants), no separate spec language | Low — pure Python, integrates with pytest, can drive real HTTP calls | Can enable a `ThreadPoolExecutor`/parallel step mode for concurrency (bolt-on, less mature than sequential); no native migration concept, but "run migration" can be one of the rules |
| Schemathesis (OpenAPI/GraphQL property testing, built on Hypothesis) | Fuzzes requests generated from the OpenAPI schema; checks status codes, response-schema conformance, server errors; has stateful/"links" mode for multi-step workflows | OpenAPI/GraphQL schema (not your invariants — needs custom "checks" for domain invariants) | Low — point it at the existing OpenAPI spec, add custom checks for domain invariants | Can run with `--workers` for concurrent request load, but that's throughput, not treating concurrency as part of the correctness model |
| quickcheck-state-machine / quickcheck-dynamic (Haskell), jqwik (Java), gopter (Go) | Same idea as Hypothesis stateful testing in other languages; pre/postconditions on an abstract model | Host language | Low-Medium depending on language fit (project prefers Python/Rust/Java/Go — jqwik is a direct fit for Java) | Same caveat as Hypothesis — sequential by default, some libraries have parallel/"race condition" modes |
| Deterministic simulation testing — madsim / turmoil (Rust) | Runs real async code against a simulated network/clock/disk; can inject faults and replay a failing seed exactly | Rust code + your own assertions (no separate spec language) | High if system isn't Rust/async-Rust already; Medium if it is | Yes — this is exactly the design point: interleave concurrent tasks + inject faults deterministically. Migration = another simulated task |
| Deterministic simulation testing — Antithesis (SaaS, hypervisor-level) | Runs unmodified containers under a deterministic hypervisor, fuzzes inputs/faults/schedules, gives byte-identical replay of failures; you supply "test properties"/assertions via SDK | Assertions via SDK (`sometimes`/`always`) in Go/Java/Python/Rust/JS/.NET/C++, not a logic spec | High — described by Antithesis itself as "a complex, resource-intensive undertaking"; commercial, used by etcd/WarpStream | Yes, language-agnostic since it's hypervisor level; would need migrations expressed as one of the simulated workloads |

## Per-technique assessment

**TLA+ trace validation (Pressler → Kuppe/Merz/TraceLink).** Strength: reuses
the exact spec used for model checking, so "verify actual behavior" and
"check invariants before code exists" share one artifact. Weakness,
confirmed by both MongoDB's postmortem and the 2024 SEFM paper's own stated
limitations: the hard part isn't running TLC on a trace, it's (a)
instrumenting the implementation to emit exactly the variables/actions the
spec talks about, and (b) keeping spec and code from drifting — MongoDB's
spec assumed leader step-down/step-up were atomic, the real code didn't, so
no trace ever matched. A trace-check failure is therefore ambiguous (bug vs.
spec abstraction mismatch), which undercuts a "trustworthy" signal unless the
spec is unusually tight. Best fit: specs written **with trace-checking as a
goal from day one** (TraceLink generates both code and log statements from
the same PlusCal source, closing the gap by construction).

**MongoDB eXtreme Modelling / test-case generation.** The generation
direction (spec → generated test cases with an oracle) beat the
trace-checking direction in MongoDB's own numbers (2 weeks, 100% branch
coverage, found a real bug vs. 10+ weeks, 0 bugs). Lesson: favor "generate
tests/traffic from the spec and check outcomes" over "instrument prod and
replay logs against the spec" for a fast, believable oracle.

**Jepsen + Elle.** Mature (7+ years across Cassandra, CockroachDB, TiDB),
with a well-documented consistency-model catalogue; input is just a history
of ops with process/time ordering, which request-logging middleware can
emit without deep code instrumentation. Blind spot: checks *data-access
consistency* (snapshot isolation, etc.), not arbitrary application invariants
("invoice line items sum to its total"), and has no first-class concept of
"a migration ran" — schema changes break the "same key means the same
thing" assumption the checker relies on. Good as one layer, not a
replacement for higher-level invariant checking.

**Porcupine.** Simplest mental model: write a small sequential Go model,
feed it a concurrent history, get yes/no on linearizability (used at scale
by etcd/TiDB/AWS MemoryDB). Doesn't speak to migrations, and only checks
linearizability — a property the brief explicitly says may be relaxed for
performance. Useful for the serializable starting point, less so once the
system deliberately allows non-linearizable histories.

**P monitor machines / PObserve.** Conceptually the closest fit to milestone
4: P already separates the system model from spec/observer machines, and
PObserve extends the idea to structured production logs (AWS's own framing:
closing the design-time/runtime gap). Cost: commits to P as the spec
language and needs event logging aligned to the spec's vocabulary — same
discipline TLA+ trace validation needs.

**LTL/MTL runtime monitors (Reelay, LoomRV, etc.).** The most literal
"compile the invariant, stream events, get an alarm" pipeline — closest to
how a developer's natural-language invariant would become a checker, with
clean boolean/counterexample output. Still mostly research tools (small
communities, cyber-physical-systems focus, not web/DB-oriented); no
off-the-shelf notion of "concurrent API + migration," so we'd build the
event vocabulary ourselves. Worth prototyping precisely because that
translation step is what the project's step 2→4 needs.

**Hypothesis stateful testing + Schemathesis.** Lowest activation energy,
and it drives the actual web API rather than a model of it. Weakness: the
"spec" is hand-written pre/postcondition code, not a separate formal
language, with no model-checker-style exhaustiveness guarantee; concurrency
support is a bolted-on parallel mode, not modeled concurrency semantics.
Schemathesis adds schema-conformance fuzzing for free but its invariants are
generic unless custom checks are added. Pragmatic "boring but works today"
option and a likely supporting piece (e.g., generate call sequences from the
same abstract model that also feeds the TLA+/P spec) rather than the
primary spec-conformance oracle.

**Deterministic simulation testing (madsim/turmoil, Antithesis, FoundationDB
style).** Best matched to "requests + migrations concurrently" as a
*testing* concern — it finds bugs via fuzzed schedules/faults rather than
checking conformance to a written spec, though invariants can be embedded as
in-simulation assertions. Rust-native madsim/turmoil fit the project's
language list well and let a migration task and request-handling tasks run
as ordinary concurrent tasks under one deterministic scheduler with exact
seed replay. Antithesis generalizes this to any language via a hypervisor
but is commercial and, per its own docs, a heavier lift — a later-stage
option, not a 1-2 day prototype.

## Fit for the workflow

Mapping onto the intended workflow (invariants → formal spec → verify actual
behavior → agent optimizes with constraints as hard boundaries):

- **Step 4 ("verify actual system behavior")** is best served, in the near
  term, by a *layered* approach rather than a single tool: (1) Elle/Porcupine-
  style history checking for the DB-consistency layer, since it needs only a
  request/response log we'd want anyway; (2) Hypothesis/Schemathesis-style
  model-based testing directly against the running API for
  application-level invariants, since it's cheap and testable this week;
  (3) TLA+/P trace validation or monitor machines as the *aspirational*
  tight loop back to the same spec used for model checking, once a spec
  is written specifically with observability in mind (learn from MongoDB:
  write for trace-checking, don't retrofit).
- **Migrations running concurrently with requests** are not natively modeled
  by any surveyed tool — this is a gap the project's own spec work
  (`05-db-migrations-concurrency.md`) needs to fill; runtime verification
  tools only need "a migration" to be representable as an event/operation in
  whatever history/log format the checker consumes.
- **Trustworthy pass/fail signal for an optimizing agent** is a strong reason
  to prefer techniques with a hard, checkable oracle over "we didn't find a
  counterexample" fuzzing: Elle/Porcupine give crisp anomaly reports; TLC
  trace validation gives a clear violated-invariant trace; DST fuzzing (madsim,
  Antithesis) gives "found a failing seed" but absence of a finding is weaker
  evidence than a model-checked property. If the agent is meant to treat a
  green run as a hard boundary, favor tools with well-defined completeness
  properties (e.g. Elle's cycle detection is sound for the anomalies it
  targets) over "ran N random schedules and nothing broke."

## Prototype ideas (1-2 day scale)

1. **Request-history linearizability/consistency check.** Add lightweight
   middleware to a toy Python/Go API (e.g. a key-value CRUD service backed
   by Postgres) that logs each request as a Jepsen-style op
   (`{process, type, f, key, value, :ok/:fail, start, end}`). Run Porcupine
   (if a linearizable register model suffices) or Elle (if list-append/
   read-write register semantics fit) against a burst of concurrent load,
   confirm both tools flag an intentionally injected bug (e.g. remove a
   transaction's isolation level) and pass on the fixed version.
2. **Hypothesis stateful model of the API + invariant.** Write a
   `RuleBasedStateMachine` in Python with rules mirroring 3-4 API endpoints,
   an in-memory model tracking the developer's stated invariant (e.g. "sum
   of ledger entries per account never goes negative"), and postconditions
   that call the *real* running API (via `requests`) rather than a mock.
   Include one rule that "runs a migration" (e.g. adds a column with a
   default) mid-sequence, to see whether Hypothesis's shrinker isolates a
   minimal failing interleaving.
3. **Toy TLA+ trace-validation loop.** Take a tiny existing TLA+ spec (a
   2-3 action counter/queue) written specifically to be trace-checked
   (variables = exactly what's logged), instrument a minimal Python or Go
   service to emit an action log matching the spec's vocabulary 1:1, and
   use TLC's trace validation to check a handful of recorded runs, including
   one deliberately buggy build. Goal: measure how much instrumentation
   discipline is required to keep spec and code from drifting, since that
   was the single biggest cost driver in every account surveyed.
4. **madsim/turmoil migration-vs-request race.** In Rust, build a minimal
   async service with two concurrent tasks: one serving reads/writes to a
   shared in-memory table, one performing a "migration" (e.g. renaming/
   backfilling a field) after a random delay. Run under turmoil/madsim with
   many seeds to see how quickly it surfaces a read-during-migration
   inconsistency, and confirm the failing seed replays deterministically.
   This most directly rehearses the brief's core concurrency scenario.

## Sources

- [Verifying Software Traces Against a Formal Specification with TLA+ and TLC (Pressler)](https://pron.github.io/files/Trace.pdf)
- [Conformance Checking at MongoDB: Testing That Our Code Matches Our TLA+ Specs](https://www.mongodb.com/blog/post/engineering/conformance-checking-at-mongodb-testing-our-code-matches-our-tla-specs)
- [eXtreme Modelling in Practice (VLDB 2020 paper)](http://vldb.org/pvldb/vol13/p1346-davis.pdf)
- [Modular verification of MongoDB Transactions using TLA+ (Demirbas blog, 2025)](http://muratbuffalo.blogspot.com/2025/05/modular-verification-of-mongodb.html)
- [Validating Traces of Distributed Programs Against TLA+ Specifications (SEFM 2024 / arXiv 2404.16075)](https://arxiv.org/abs/2404.16075)
- [Validating System Executions with the TLA+ Tools — TLA+ Conf 2024 (Kuppe slides)](https://conf.tlapl.us/2024/MarkusAKuppe-ValidatingSystemExecutionsWithTheTLAPlusTools.pdf)
- [Trace Validation for TLA+ — TLA+ Community Event slides (Merz et al., 2024)](https://conf.tlapl.us/2024-fm/slides-merz.pdf)
- [Jesse's 2025 TLA+ Community Event notes — TraceLink/PGo](https://emptysqua.re/blog/2025-tlaplus-community-event/)
- [jepsen-io/elle (GitHub)](https://github.com/jepsen-io/elle)
- [Jepsen homepage / blog](https://jepsen.io/)
- [anishathalye/porcupine (GitHub)](https://github.com/anishathalye/porcupine)
- [P Monitors — P language docs](https://p-org.github.io/P/manual/monitors/)
- [Systems Correctness Practices at Amazon Web Services (ACM Queue, PObserve)](https://queue.acm.org/detail.cfm?id=3712057)
- [Reelay: Online Temporal Logic Monitoring Framework](https://arxiv.org/html/2604.22384v1)
- [Multi-Property Temporal Logic Monitoring (LoomRV)](https://arxiv.org/html/2605.13668)
- [Hypothesis: Stateful testing docs](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- [Rule Based Stateful Testing (Hypothesis Works blog)](https://hypothesis.works/articles/rule-based-stateful-testing/)
- [Schemathesis homepage](https://schemathesis.io/)
- [quickcheck-state-machine (Haskell, GitHub)](https://github.com/stevana/quickcheck-state-machine)
- [jqwik stateful testing blog post](https://blog.johanneslink.net/2018/09/06/stateful-testing/)
- [Deterministic simulation testing — Antithesis docs](https://antithesis.com/docs/resources/deterministic_simulation_testing/)
- [madsim-rs/madsim (GitHub)](https://github.com/madsim-rs/madsim)
- [Deterministic simulation testing for async Rust — S2.dev blog](https://s2.dev/blog/dst)
- [Deterministic Simulation Testing in Rust: A Theater Of State Machines — Polar Signals](https://www.polarsignals.com/blog/posts/2025/07/08/dst-rust)
- [awesome-deterministic-simulation-testing (curated list)](https://github.com/ivanyu/awesome-deterministic-simulation-testing)
- [How etcd Solved Its Knowledge Drain With Deterministic Testing — The New Stack](https://thenewstack.io/how-etcd-solved-its-knowledge-drain-with-deterministic-testing/)

## Open questions

- Can the project's eventual formal spec be written in a "trace-checking
  first" style from the start (à la TraceLink) rather than retrofitted, to
  avoid MongoDB's failure mode?
- What request/response logging does the target web API already have (or
  can cheaply add) that would double as a Jepsen/Elle-style history without
  bespoke instrumentation?
- Is linearizability actually the right target consistency model given the
  brief's explicit rejection of full serializability, or should Elle's
  weaker consistency models (e.g. snapshot isolation, causal) be the
  baseline oracle instead of Porcupine's linearizability?
- How should a schema migration be represented in a recorded history/trace
  so that Elle/Porcupine-style checkers (which assume stable key semantics)
  don't produce false positives across a migration boundary?
- Is a commercial DST platform (Antithesis) worth evaluating for M3, or does
  the project's Rust-friendly stance make madsim/turmoil sufficient and
  cheaper to try first?
- Which invariants from step 1 (natural language) map naturally to
  "consistency anomaly" (Elle's language) vs. "temporal formula" (LTL
  monitor) vs. "pre/postcondition" (Hypothesis) — this likely determines
  which of the above tools ends up as the primary runtime oracle.
