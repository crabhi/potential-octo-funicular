# Online DB migrations concurrent with requests: formal treatment

Date: 2026-07-30
Status: draft

## TL;DR

- The **expand/contract (parallel change) pattern** is the near-universal
  industry answer to "migrate schema while serving traffic": add, then
  dual-write/backfill, then switch reads, then remove. It is described only
  informally (blog posts, tool docs) almost everywhere except one paper.
- The **canonical formal treatment is Google F1's "Online, Asynchronous
  Schema Change in F1" (Rae et al., VLDB 2013)**. It defines two anomaly
  classes — *orphan data* and *integrity* (missing-element) anomalies —
  introduces *delete-only* / *write-only* intermediate schema states, and
  proves that if all servers are within one schema version of each other,
  a schema change decomposed into these states cannot corrupt data. This is
  the template to imitate for the project's own formalization.
- No widely used migration tool (pgroll, Reshape, gh-ost,
  pt-online-schema-change) publishes a formal correctness argument; all rely
  on the same informal expand/contract intuition plus operational testing.
  **This is a genuine gap** — and an opportunity for this project's tooling.
- Modeling this problem is really a **transaction-isolation modeling
  problem plus a schema-versioning dimension**: you need a base isolation
  spec (Adya histories, or Crooks et al.'s client-centric read-states model)
  extended with "which schema version does this operation see."
- Existing TLA+ specs of snapshot isolation (e.g. will62794/snapshot-isolation-spec,
  the tlaplus/Examples SnapshotIsolation spec) model reads/writes on a fixed
  schema only — **none model DDL/schema evolution**. Building that
  extension is novel, tractable work, not a re-implementation of existing art.
- Jepsen/Elle is the right complementary tool for the **empirical** side:
  it detects Adya anomalies from black-box histories and could be extended
  to flag anomalies that specifically arise from *mid-migration* schema
  states (e.g. a read observing a column that a concurrent contract phase
  is dropping).

## Key prior art

**F1 online schema change (Rae, Rollins, Shute, Sodhi, Vingralek, VLDB 2013,
"Online, Asynchronous Schema Change in F1").** F1 is Google's globally
distributed DB (backing AdWords) with stateless servers and no global
membership/consensus on "current schema" — servers pick it up
asynchronously. Core contribution: a *formal model of correctness for
schema changes*. A change is consistency-preserving iff it never causes an
**orphan data anomaly** (an element exists that shouldn't, per the current
logical schema) or an **integrity anomaly** (an element that should exist is
missing/unreadable). Naive single-step changes (e.g. adding a NOT-NULL
column, adding an index) can cause either anomaly when two servers straddle
old/new schema at once. The fix: decompose any change into a sequence
through **delete-only** and **write-only** intermediate states (delete-only:
can be deleted/updated but not read by app code; write-only: can be
insert/update/deleted but not read) so any two servers at most one version
apart produce mutually consistent views. Informal theorem: decompose this
way, and guarantee via a lease protocol that no server lags more than one
version, and no anomaly occurs regardless of transaction interleaving. It
assumes F1's own transaction model (Spanner-like snapshot/external
consistency) as substrate — schema-version safety is composed *on top of*
an isolation guarantee taken as given, not re-derived. This composability
(isolation invariants + schema-version invariants, proved separately then
combined) is exactly the decomposition our project should reuse. Source:
https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/41376.pdf
(secondary summary: https://blog.acolyer.org/2015/01/07/online-aysnchronous-schema-change-in-f1/).

**Expand/contract (parallel change) pattern.** Practitioner pattern, no
single canonical citation; popularized by Fowler/ThoughtWorks-adjacent
writers and, more recently, pgroll/Reshape/Xata blog posts. Structure:
Expand (add new schema elements, backward compatible) → Migrate/Backfill
(populate new structures while old paths keep working) → Contract (remove
old elements once all readers have moved on). Natural invariants to state
formally: (1) at every point exactly one of {old-only, dual, new-only}
phases holds per element; (2) every reachable schema state during migration
is valid for *some* declared app-version's expectations; (3) no phase
transition happens before all connected app instances are past the version
that depends on the state being removed (an ordering/liveness precondition,
not just safety). None of the sources found state these as formal
temporal-logic invariants — always prose. This gap is what this project's
spec layer could fill.

**Isolation-level formalizations usable as substrate:**
- **Adya (PhD thesis 1999, w/ Liskov & O'Neil, "Generalized Isolation Level
  Definitions").** Isolation via *histories*: a partial order of
  transactions with dependency edges (write-read, write-write,
  anti-dependency); anomalies (G0, G1a/b/c, G-single, G2, ...) are forbidden
  dependency-graph cycles. This dependency-graph vocabulary is what every
  modern isolation checker, including Elle, still uses.
- **Cerone et al. (2015)**: *visibility* relation between transactions plus
  a global *arbitration* (commit) order. Cleanly axiomatic but cannot
  express isolation levels weaker than Read Atomic (e.g. plain Read
  Committed), since it assumes atomic visibility of a transaction's writes.
- **Crooks, Pu, Estrin, Alvisi ("Seeing is Believing: A Client-Centric
  Specification of Database Isolation", PODC 2017).** Isolation purely in
  terms of client-observable states: each read picks a "read state" from a
  totally ordered sequence of database states; guarantees constrain which
  states a read may pick relative to the issuing transaction's other
  reads/writes. Handles weaker levels (Read Committed) that visibility-based
  models can't, and organizes SI variants into a hierarchy. Follow-up
  **"Automated Validation of State-Based Client-Centric Isolation with
  TLA+"** (2021, https://link.springer.com/chapter/10.1007/978-3-030-67220-1_4)
  mechanizes and model-checks this — a direct technique template for us
  (state-based isolation spec + TLC).
- **will62794, "Modern Views of Transaction Isolation"** (2025,
  https://will62794.github.io/formal-methods/specification/2025/03/17/transaction-isolation-models.html)
  is a good 2025 synthesis comparing Adya/Cerone/Crooks before reading primaries.
- **TLA+ snapshot isolation specs**: `tlaplus/Examples`
  `specifications/SnapshotIsolation` and https://github.com/will62794/snapshot-isolation-spec.
  Both model a fixed key space with begin/read/write/commit actions,
  checking SI anomalies (read-only anomaly, write skew); **neither models
  schema/DDL** — the schema is static. This is our extension point.

## Tools inventory

| Tool | Guarantees claimed | Formalized? | Notes |
|---|---|---|---|
| **F1 protocol** (Google, internal) | No orphan-data/integrity anomalies given ≤1 version skew + lease protocol | Yes — the paper's own contribution, with proof sketch | Not a standalone tool; absorbed into Spanner-family thinking. Best available formal template. |
| **pgroll** (Postgres, Xata, OSS, active) | Old+new schema versions both work simultaneously via versioned views + triggers | No — mechanism documented, no proof or model-based tests | Architecturally close to F1's write-only/delete-only states (a view hides/exposes columns), but correspondence never stated by authors. |
| **Reshape** (Postgres, Rust, experimental) | Same expand/contract goal via views + triggers | No | Smaller, less active than pgroll; same informal story. |
| **gh-ost** (MySQL) | Triggerless; replays binlog into shadow table, avoids locking | No; argued operationally (throttling, checksums, atomic cut-over) | Accepts replication lag; "eventual convergence + atomic rename" argument never formalized. |
| **pt-online-schema-change** (Percona, MySQL) | Trigger-based shadow table kept strictly consistent (no lag) | No | Correctness rests on MySQL trigger atomicity, argued informally. |
| **Jepsen/Elle** | Checker, not a migration tool: detects Adya anomalies (G0, G1a/b/c, G-single, G2) from black-box histories | Yes — directly implements Adya's definitions (arXiv 2301.07313 covers the SI-checking algorithm) | No DDL/schema-change support; checks a fixed value space. Would need extension to treat schema-version as observed state. |

## How to model it

Sketch of a state-based model that composes an isolation spec (Crooks-style
or Adya-style) with an F1-style schema-version dimension. This is meant as
a starting point for a TLA+ (or similar) spec, not final syntax.

**State variables**
- `schemaState[elem] \in {Absent, DeleteOnly, WriteOnly, Present}` per
  schema element (column, index, constraint) — F1's intermediate-state
  vocabulary.
- `migrationPhase \in {Expand, Backfill, Contract, Done}`
- `appInstances`: running server/request-handler instances, each tagged
  `appVersion \in {N, N+1}`.
- `db`: the row/column data store, abstract map from key to record, whose
  shape depends on which elements are `Present`/`WriteOnly`.
- Per-request state (Crooks-style): a `readState` (snapshot index into a
  totally ordered sequence of committed database states) plus
  `writesPending`.
- `history`: append-only op log for Adya/Elle-style dependency analysis.

**Actions**
- `RequestBegin(req, appVersion)` — pins a snapshot per the target isolation
  level (SI pins at begin; READ COMMITTED re-reads latest committed state
  per statement).
- `RequestRead/Write(req, elem)` — guarded by
  `CompatibleWithSchemaState(appVersion, elem, schemaState[elem])`: e.g. an
  `appVersion=N` request reading a `DeleteOnly` column is disallowed
  (app must not read what migration is retiring); an `appVersion=N+1`
  request writing an `Absent` column is disallowed.
- `RequestCommit(req)` — standard isolation-level commit/conflict rule.
- `MigrationStep` — advances one element through `Absent -> WriteOnly ->
  Present` (expand) or `Present -> DeleteOnly -> Absent` (contract); each
  step is atomic and interleavable with any request action from either
  app version.
- `BackfillStep(elem, rowRange)` — a migration-driven write filling the new
  representation for existing rows; must obey the same isolation rules as
  an ordinary write ("backfill is just another transaction").

**Example invariants**
- *No orphan/integrity anomaly (F1-style)*: for every committed request `r`
  with `appVersion=v`, every element `e` it reads/writes satisfies
  `SchemaCompatible(v, schemaState[e])` at `r`'s effective time.
- *No request observes a column that is gone*: a request should never get
  a "column not found" error mid-flight — the practical pain point
  expand/contract exists to prevent.
- *Backfill sees a consistent snapshot*: `BackfillStep` reads rows under the
  same isolation level requests use, so it cannot read half-written rows
  from a concurrent request — backfill is "just another transaction," not
  exempt from isolation.
- *Version skew bound*: `∀ i,j ∈ appInstances: |i.appVersion - j.appVersion| ≤ 1`
  (F1's lease invariant) — a deployment-orchestration precondition; violating
  it invalidates every other invariant's proof.
- *Contract only after drain*: `migrationPhase=Contract ⇒ ∀ i ∈ appInstances:
  i.appVersion ≥ N+1` — no old-version instance remains that needs the
  element being dropped.
- *Isolation preserved end-to-end*: the underlying history (ignoring schema
  bookkeeping) still satisfies the chosen isolation level's definition —
  migration machinery must not *weaken* the isolation the app relies on.

This is naturally a **refinement**: start with all requests serializable
(matches the brief's stated fallback), get the schema-version invariants
right there, then relax to snapshot isolation / READ COMMITTED and re-check
the same invariants still hold — anomalies like G2 (anti-dependency cycles)
only appear once serializability is dropped.

## Fit for the workflow

- Slots cleanly into the project's 5-step workflow: "developer states
  invariants" ("no request ever sees a half-migrated row," "app N and N+1
  never disagree about column X's meaning") maps directly onto the
  schema-state and version-skew invariants above.
- **F1's delete-only/write-only decomposition is a reusable design pattern
  the LLM agent can be taught to apply automatically**: given a target
  schema diff, mechanically expand it into F1-safe intermediate steps, then
  verify each step against the invariants — a concrete, scoped M3 candidate.
- Isolation-level correctness and schema-version correctness are
  **separable concerns** (per F1's own proof structure): adopt an existing
  isolation spec (Crooks-style, or the will62794/tlaplus Examples spec) as
  a black box and author only the schema-versioning layer on top — far
  less new formal work than deriving isolation semantics from scratch.
- Elle (or a variant) is the natural empirical backstop for workflow step 4
  ("verify actual system behavior... runtime/trace verification"):
  instrument the real API + migration tool, record a Jepsen-style history
  tagged with schema-version metadata per operation, check it against both
  the isolation definition and the new schema-transition invariants.

## Prototype ideas (1-2 day scale)

1. **Minimal TLA+ model of F1's delete-only/write-only protocol alone**
   (assume serializable, per the brief's suggested starting point). Model
   one column add + one column drop through the 4-state lifecycle, two app
   versions, and check the orphan/integrity invariants with TLC on a small
   bounded model. Reuses F1's published proof structure directly, so it is
   low-risk and gives a template the project can show the developer.
2. **Extend an existing snapshot-isolation TLA+ spec** (e.g. the
   tlaplus/Examples one) with a single mutable schema element
   (`Absent/WriteOnly/Present`) and re-check whether known SI anomalies
   (write skew, read-only anomaly) still hold, plus add the new "no read of
   an absent column" invariant. Tests the refinement-path claim in the
   brief (start serializable, extend to SI) on the smallest possible
   schema-migration example.
3. **Elle-based empirical harness**: stand up a toy web API in front of
   Postgres, run pgroll for a real expand/contract migration concurrently
   with a Jepsen-style load generator (tagging each op with schema-version),
   dump the history, and run it through Elle (or a small custom Adya-cycle
   checker) to see whether pgroll's dual-write triggers actually preserve
   the isolation level the app expects — cheapest way to get real signal on
   whether "tools claim correctness but don't formalize it" (this note's
   main finding) translates into observable anomalies.

## Sources

- F1 paper: https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/41376.pdf ,
  https://research.google/pubs/pub41376/ , DOI https://dl.acm.org/doi/10.14778/2536222.2536230 ,
  summary: https://blog.acolyer.org/2015/01/07/online-aysnchronous-schema-change-in-f1/
- Expand/contract: https://xata.io/blog/pgroll-expand-contract ,
  https://www.prisma.io/dataguide/types/relational/expand-and-contract-pattern ,
  https://blog.thepete.net/blog/2023/12/05/expand/contract-making-a-breaking-change-without-a-big-bang/
- pgroll: https://pgroll.com/ , https://github.com/xataio/pgroll , https://xata.io/blog/pgroll-schema-migrations-postgres
- Reshape: https://github.com/fabianlindfors/reshape
- gh-ost vs pt-online-schema-change: https://www.bytebase.com/blog/gh-ost-vs-pt-online-schema-change/
- Crooks et al., "Seeing is Believing": https://blog.acolyer.org/2020/11/30/seeing-is-believing/ ,
  thesis: https://nacrooks.github.io/bibliography/publications/thesis.pdf
- "Automated Validation of State-Based Client-Centric Isolation with TLA+": https://link.springer.com/chapter/10.1007/978-3-030-67220-1_4
- will62794, "Modern Views of Transaction Isolation" (2025): https://will62794.github.io/formal-methods/specification/2025/03/17/transaction-isolation-models.html
- TLA+ SI specs: https://github.com/will62794/snapshot-isolation-spec ,
  https://github.com/tlaplus/Examples/tree/master/specifications/SnapshotIsolation
- Jepsen/Elle: https://github.com/jepsen-io/elle ,
  https://github.com/jepsen-io/elle/blob/main/README.markdown ,
  paper: http://www.vldb.org/pvldb/vol14/p268-alvaro.pdf , efficient SI checking: https://arxiv.org/pdf/2301.07313
- Related technique (MongoDB TLA+ verification): http://muratbuffalo.blogspot.com/2025/05/modular-verification-of-mongodb.html

## Open questions

- Is there a published formal treatment of **backfill correctness**
  specifically (the "migrate" step's data-copy, vs. the schema-state
  machine)? Not found in this pass — worth a follow-up search on "online
  index build" / "concurrent backfill" (Postgres's own `CREATE INDEX
  CONCURRENTLY` internals may have a semi-formal safety argument) and
  vendor blogs (Spanner, CockroachDB online schema change docs).
- Does the project want to model **constraints** (NOT NULL, foreign keys,
  uniqueness) as first-class invariants distinct from column
  presence/absence? F1's taxonomy hints at this (integrity anomaly ~
  constraint violation) but the paper's constraint-specific detail wasn't
  extracted in this pass — the full PDF text extraction failed in this
  environment (cryptography/cffi toolchain issue with pypdf/pdfminer; a
  cached copy sits at
  `/root/.claude/projects/-home-user-potential-octo-funicular/3a6c8640-3eda-5502-b921-894ad231b3d0/tool-results/webfetch-1785420775431-gvhpia.pdf`
  for a future pass with a working extractor).
- Which isolation level does the target system's database actually run at
  (Postgres default READ COMMITTED vs. explicit SERIALIZABLE)? Determines
  which existing formal spec (Crooks client-centric for weak levels, or a
  simpler serializable model) is the right starting substrate — pin this
  down with the developer before M3.
