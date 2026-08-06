# Rung 5 expanded: proofs in the code / code from the spec

**Date, status:** 2026-08-06, draft (desk research on top of tracks D/E/G/L;
three parallel research sweeps, claims spot-checked against primary sources).
Context per CLAUDE.md: evaluated for a **regular web SaaS application** built
by LLM agents under frozen, machine-checked gates.

Rung 5 of the assurance ladder (note 09 / slide "The honest question") is
where the model↔code boundary stops being tested and starts being *removed*:
either the proof lives in the code, or the code is generated from the proven
artifact. This repo has four rung-5 results already — Dafny authz kernel
proven and compiled to Go (track D), the session state machine proven in
Dafny (track L), `Grant<Op>` compile-error boundaries (track G), Kani vs
exhaustive measured (track E). This note asks: **which rung-5 shapes scale
across a whole SaaS when LLM agents do the work** — and which are dead ends
for our setting.

## TL;DR / verdict

Rung 5 is not one approach but **five distinct patterns** with very
different per-feature economics. Ranked for our setting:

1. **Verified engine + small DSL surface** ("prove once, rule forever") —
   the pattern industry actually shipped: AWS Cedar (Lean-proven authorizer
   + symbolic policy analysis, in production via Amazon Verified
   Permissions), Bedrock Automated Reasoning checks (GA 2025), AgentCore
   Policy (NL→Cedar with a symbolic feedback loop, 2026). Marginal cost of
   a new feature: **zero prover calls** — the LLM writes DSL, a sound
   analyzer checks it. This independently confirms the 3DGen pattern we
   flagged in note 11 (falsifier F3) — three separate AWS products now have
   this shape.
2. **Proven kernel, generated and embedded** — our track D, validated at
   cloud scale: AWS rewrote the IAM authorization engine in Dafny compiled
   to Java, deployed at ~10⁹ authorizations/second (ICSE 2025). Dafny is
   the LLM sweet spot (DafnyPro 86%, AxDafny 92.7% on DafnyBench, 82% on
   the POPL'26 vericoding benchmark). Per-feature cost: one proof per
   kernel change, LLM-affordable.
3. **Proofs in the code** (Verus/Kani/Flux on Rust) — real-systems LLM
   evidence arrived in force: VeruSAGE completes 81% of 849 proof tasks
   from 8 real Verus-verified systems at ~$5.61 and ~7 min per task —
   agent proof maintenance now fits ordinary CI budgets. Go (Gobra,
   3.9–10.4 spec lines per code line), TypeScript (nothing static
   survives), and Python (CrossHair = counterexamples, not proofs) are
   honest "no" answers; **this pattern is Rust-only in practice**.
4. **Types as by-construction boundaries** — our track G. Cheapest rung-5
   pattern (ordinary compiler, zero solver, zero CI cost); the evidence is
   constructive, not statistical. Extends to typestate/session types; on
   TS edges, branded types are the ceiling.
5. **Verified runtime enforcement** — note 10's track O. Monitor synthesis
   from temporal specs is academically active, production-thin. The
   striking finding: **an invariant→Postgres-constraint/trigger compiler
   does not exist** (theory ready: invariant confluence, CISE), and
   neither does a verified schema-migration tool — two genuine gaps that
   overlap exactly with what this repo already built.

**The unoccupied territory is our domain.** Every vericoding benchmark is
single-function algorithmic code; every production verified-business-logic
artifact (AWS authz engine, Cedar, the Dafny-written AWS Encryption SDKs)
was hand-written by verification experts. **No published result exists of
LLM-generated, machine-verified CRUD handlers, billing state machines,
tenancy isolation, or schema migrations.** The intersection — LLM-vericoded
SaaS logic under frozen specs — is precisely this project, and nobody is
publishing there yet.

Two falsifier-shaped results from the sweep, both supporting our
guardrails: **AxDafny's verified-but-undeployable finding** (of 75 verified
solutions run as Python, only 32 passed — 39 timed out, 4 OOM'd: verified
functional correctness says nothing about resources; gates need the P5
benchmark direction too — guardrail 2), and **VeriBench's theorem-coverage
gap** (agents get 100% compilation but state the *intended* theorem ≤15.6%
of the time: spec formulation, not proof search, is the bottleneck —
guardrail 5).

## Where rung 5 stands in this repo

| Artifact | Pattern | Status |
|---|---|---|
| `examples/cms/dafny-authz/` (track D) | 2 — proven kernel → Go, embedded | done; boundary caveat |
| Track L session-machine proof | 2 — proven twin of real code | done; extraction-fidelity gap |
| `Grant<Op>` tokens (track G) | 4 — compile-error boundary | done |
| Kani spike (track E) | 3 — bounded proof of Rust decision | parked until unbounded ids |
| `examples/cms/verus-spike/` | 3 | blocked (proxy); Dafny stands in |
| Note 11 F3 / P-F\*2 proposal | 1 — DSL + pre-verified checker | proposed, now industry-confirmed |

## Pattern 1 — verified engine, rules in a small DSL

The shape: verify the engine **once** (in Lean/F\*), constrain users *and
LLMs* to a small analyzable DSL, make every analysis counterexample-
producing, treat NL→DSL translation as untrusted with a symbolic feedback
loop. Per-feature proof cost: zero.

**Cedar is the complete worked example.** The evaluator, authorizer, and
validator have executable Lean models (~10× smaller than the production
Rust) with mechanized proofs (forbid-trumps-permit, default-deny, validator
soundness); the Lean↔Rust gap is closed by millions of differential-test
inputs per release (the Lean model executes at ~5µs/case, so this is
cheap); releases are blocked unless model, proofs, and differential tests
are current. Since June 2025, **Cedar Analysis** compiles policy sets to
SMT (cvc5) for equivalence/permissiveness/shadowing/conflict checking — and
the symbolic compiler is itself **proven sound and complete in Lean**
(SymCert, FMCAD 2026), so every verdict carries a concrete distinguishing
request. That is our P2 oracle (contradiction/vacuity/witness with
machine-readable verdicts), productized for authorization. Cedar is CNCF
Sandbox (Oct 2025) and backs Amazon Verified Permissions.

**The LLM loop exists too.** AgentCore Policy (2026): admins state tool
permissions in NL; an LLM translates to Cedar; generated schema validation
plus Cedar Analysis (grant-everything/deny-everything/impossible-condition
detection) feed errors back to the LLM; default-deny envelope; the LLM is
explicitly an untrusted actor. Same shape at the answer level: Bedrock
Automated Reasoning checks (GA Aug 2025) extract typed rules (surfaced as
editable SMT-LIB) from NL policy docs and check each LLM answer with a
solver, returning `VALID / INVALID / SATISFIABLE / IMPOSSIBLE /
TRANSLATION_AMBIGUOUS` — the verdict taxonomy P2 copied. (The marketed "up
to 99% verification accuracy" has no published methodology — treat as
unconfirmed.)

Variants of the same pattern: 3DGen/EverParse (agents write the 3D DSL, a
pre-verified F\* toolchain emits proven-safe parsers — ICSE 2025, no direct
successor system); Imandra's CodeLogician (LLM builds an IML model of
decision logic, the reasoning engine does exhaustive region decomposition —
deployed in financial matching logic); DMN decision-table analysis
(overlap/completeness checking; academic tooling only). Event-B has a new
FSE 2026 LLM-agent result at the *model* level, but B-method code
generation remains certification-budget territory; the transferable part is
the shape, not the toolchain.

**Why this ranks first for us:** guardrails 5 (translate/validate), 6
(counterexample currency), and 8 (boundaries by construction) compose into
exactly this pattern, and the per-feature agent loop needs no prover at
all. What it does *not* cover: anything outside the DSL's domain. The DSL
frontier (what fits in Cedar-shaped languages) is authz, entitlements,
feature flags, quota rules — not migrations or arbitrary handler logic.

## Pattern 2 — proven kernel, generated and embedded

Track D at industrial scale. The AWS IAM authorization engine was rewritten
in Dafny and compiled to **readable, idiomatic Java** (deliberately, to
earn developer trust), deployed 2024, ~1 billion invocations/second, and —
the part that matters for guardrail 5 — the spec itself was validated by
**differential/shadow testing against 10¹⁵ production samples** before
cutover. The AWS Encryption SDK, Database Encryption SDK, and Cryptographic
Material Providers Library are likewise written in Dafny and shipped as
Java/.NET/Python/Rust/Go packages. The pattern is production-real; what's
new for us is only the LLM authorship question.

LLM evidence is the strongest of any proof language: DafnyPro 86% on
DafnyBench (Claude 3.5 Sonnet; fine-tuned Qwen 7B/14B reach 68%/70% —
guardrail 3 again); AxDafny 92.7% (new SOTA) with a proposer/reviewer loop
whose deterministic checks — a **diff-checker blocking modification of the
base program**, `assume`/`{:verify false}` bans — independently converged
on our guardrail 1; ATLAS (Cambridge+AWS) auto-synthesizes verified Dafny
training data; pure proof tasks went 68%→96% in one year. On the POPL'26
vericoding benchmark (12,504 specs; anti-cheating validation; ~9% of specs
admitted too weak): 82% Dafny / 44% Verus / 27% Lean.

Repo-relevant details: Dafny's Rust backend is still work-in-progress
(tracking issue #5561) — for our axum app the Go embedding (track D) or a
C#/Java sidecar remains the near-term path, with the kernel behind
`Grant<Op>` tokens (pattern 4) to close the boundary caveat.

## Pattern 3 — proofs in the code (Rust only, honestly)

- **Verus**: weekly releases; PLDI 2026 soundness foundation; proven
  artifacts include Anvil (OSDI'24 — verified **liveness** of real
  Kubernetes controllers, the closest thing to a proven web-infra control
  loop). VeruSAGE (849 proof tasks from 8 real systems): hands-off agent
  averages o4-mini 17% / GPT-5 50% / Sonnet 4 64% / **Sonnet 4.5 81%**,
  ~7.2 min and ~$5.61/task, including >90% of a set of proofs human
  experts had left unfinished, and 83% on contamination-free tasks.
  AutoVerus >90% on its 150-task bench; VeruSyn's 6.9M synthetic corpus
  makes a 32B open model competitive. The wall is ecosystem coverage
  (std/async) — no known Verus web-service codebase exists.
- **Kani**: function contracts (`#[kani::requires]/ensures]`) are still
  experimental (`-Zfunction-contracts`), but the AWS/Rust Foundation
  verify-rust-std campaign gives real CI numbers: 16,748 harnesses, ~69
  min CI at std scale, most projects <25 min. Track E's verdict stands —
  adopt when unbounded ids/strings enter the kernel signature.
- **Flux** (refinement types for Rust): the low-burden interface —
  annotations on signatures/structs, liquid inference fills loop
  invariants, ordinary rustc plugin; an accepted tool in verify-rust-std.
  Invariants like "balance ≥ 0" or "returned rows carry the caller's
  tenant_id" fit as indexed types; full functional correctness does not.
  No published Flux+LLM work yet — but as *types-as-specs* it is the
  natural LLM interface: the spec sits on the signature the model is
  already writing, and the verdict is fast and binary.
- **Everything else**: Gobra is sound but costs 3.9–10.4 spec lines per
  code line (VerifiedSCION) with no LLM pipeline; TypeScript has no
  surviving static verification (Refined TypeScript is dead; Effect-TS
  types error channels, not semantics; zod/io-ts are runtime); Python's
  CrossHair is an actively LLM-courting **counterexample finder** (ships
  an AGENTS.md; SpecPylot pairs it with LLM-written contracts) but not a
  prover, and Nagini is sound-but-heavy (now exposing an MCP server).
  Rust→prover translators (Aeneas→Lean, hax→F\*) work on pure sequential
  fragments — crypto-shaped, not handler-shaped.

Placement for us: pattern 3 is for the **hot, tricky, agent-optimized
paths of a Rust app** (P5's territory), not whole handlers — unchanged
from note 03, but the cost estimate dropped an order of magnitude
(VeruSAGE's $/task), and Flux adds a cheap middle tier we had not priced.

## Pattern 4 — types as by-construction boundaries

Track G shipped this: `Grant<Op>` tokens minted only by the verified
kernel; forgery and wrong-op use are pinned compile-fail tests. The sweep
adds: typestate has a peer-reviewed Rust DSL and session-type libraries
prove protocol conformance by ordinary compilation (zero CI cost), but
**no empirical study measures API-misuse reduction in the wild** — the
evidence is constructive (compiles ⇒ holds), which is exactly why it
belongs under every other pattern rather than replacing them. On TS edges,
branded/phantom types encode capability possession but nothing semantic.
F\*'s effect-indexed types (note 11) remain the strictly-stronger version
if a richer kernel is ever needed.

## Pattern 5 — verified runtime enforcement (and two gaps worth owning)

Monitor synthesis from temporal specs is real research (LoomRV, LLMon at
RV 2025) with **no production-usable product for web backends**; the
"shielding" literature has pivoted to LLM-agent runtime enforcement
(AgentSpec, VeriGuard et al.), which is adjacent to our harness but not to
our app. What the sweep surfaced instead is two concrete holes squarely in
our domain:

1. **No invariant→Postgres-constraint/trigger compiler exists.** CHECK
   can't soundly see other rows; cross-row invariants need constraint
   triggers plus explicit locking or SERIALIZABLE; the theory for "which
   invariants can the DB enforce without coordination" is done (invariant
   confluence — Bailis; CISE) but unpackaged. A compiler from our typed
   invariant schema to (a) plain constraints where sound, (b) constraint
   triggers + isolation side-conditions, (c) *residual obligations routed
   to the model checker* would make the enforcement split explicit and
   machine-checked. Nothing like it ships.
2. **No verified schema-migration tool exists.** Atlas/pgroll/Bytebase
   lint patterns; none carry a formal argument. Our P1 model + tracks
   I/J/M proofs + P3 harness is, as far as the sweep could find, the most
   complete formal treatment of online migration anywhere post-F1-paper.
   Worth stating plainly in any write-up.

Also in the semi-formal middle: VeriEQL (OOPSLA'24) does bounded SQL
equivalence **with counterexample databases** — a natural CI gate for
agent-proposed query rewrites/ORM changes (SpotIt at ICLR'26 already uses
this to show test-based text-to-SQL evaluation over-scores — "tests are
only an approximation," for SQL); Schemathesis is the mature API-boundary
fuzzer but nothing compiles *invariants* into its checks — a small third
gap adjacent to our MBT track.

## Mapping patterns to SaaS subdomains

| Subdomain | First choice | Second | Notes |
|---|---|---|---|
| Authorization / entitlements | 1 (Cedar, or own DSL + P2 core) | 2 (own Dafny kernel, track D) | both proven in production at AWS |
| Billing / lifecycle state machines | 2 (proven kernel) | 1 (Imandra-shaped decision model) | state machines are Dafny-friendly; Cedar can't express them |
| Tenancy isolation | 1 (DSL, note 11's F3) + 5 (RLS/constraints) | hyperproperty proof (track K) for leakage | per-request checks can't see leaks — note 10 |
| Schema migrations | model level (rungs 6–9: P1, I/J/M) + 5 | — | no code-level tool exists to adopt; we are the SOTA |
| Hot handler paths (Rust) | 3 (Kani bounded now, Verus/Flux as ecosystem allows) | 4 | P5's gate + a proof tier |
| API boundary / the rest | rungs 2–4 (MBT, trace validation) + 4 | 5 | proofs don't reach here yet; tests are the honest tool |

## Falsifiable predictions (scoreboard candidates)

| # | Prediction | Falsifier |
|---|-----------|-----------|
| R1 | The 10 CMS rules port to Cedar; Cedar Analysis reproduces P2's verdicts (contradiction/shadowing/vacuity) with concrete counterexample requests, and an LLM writing policies against schema validation converges in ≤ the P4 episode-2 round count | rules don't fit Cedar's fragment (e.g. workflow-state conditions), or a seeded conflict goes undetected |
| R2 | An invariant→Postgres compiler for 3 CMS/migration invariants emits constraints/triggers whose soundness side-conditions are checkable, with residual obligations discharged by the existing Quint model | every interesting invariant lands in "requires SERIALIZABLE" (the compiler adds nothing over a comment) |
| R3 | (= note 11 F3, now industry-backed) A tenant-isolation DSL + pre-verified checker needs zero per-feature prover calls and beats the P4 gate on round count | prover needed per feature, or more rounds |
| R4 | AxDafny's verified-but-slow failure mode reproduces in our loop: a repair passing the full proof gate but rejected only by P5's benchmark threshold | proof gate + feature runs alone already catch it |
| R5 | Flux expresses ≥3 of the CMS invariants as refinement types on the real axum handlers with <0.5 annotation lines per code line | invariants need full functional correctness (Verus territory) or Flux chokes on the async/ORM code |

## TCB accounting per pattern (note 10, item 9)

| Pattern | You trust |
|---|---|
| 1 (Cedar-shape) | the engine's Lean proofs + differential harness; the schema author; NL→DSL review |
| 2 (Dafny kernel) | Dafny verifier + target-language compiler; the YAML→ensures mapping; the app routing through the kernel (→ pattern 4) |
| 3 (Verus/Kani/Flux) | the verifier + rustc; spec faithfulness (VeriBench's gap lives here) |
| 4 (types) | the compiler; the sealing discipline at module boundaries |
| 5 (runtime) | the monitor/constraint compiler + the DB's isolation actually configured |

## Prototype proposals

1. **P8 — Cedar shootout (R1):** same 10 rules, fourth implementation
   (after Quint model, Rust app, Dafny kernel): Cedar policies + schema;
   run `cedar-policy-symcc` analyses; seed the known conflicts; wire an
   LLM policy-writing loop with analysis feedback. Also measures whether
   our P2 oracle is subsumed by shipped tooling for the authz slice.
   (Feasibility: crates.io reachable in this environment; no GitHub
   binaries needed.)
2. **P9 — invariant→constraint compiler spike (R2):** on P3's Postgres;
   input = the typed invariant schema from D1; output = SQL DDL + a
   machine-readable residual-obligation list consumed by the Quint gate.
3. **R5 Flux spike** rides on the existing CMS app; R3 is note 11's
   P-F\*2, unchanged; R4 is a cheap re-analysis of P4/P5 logs plus one
   seeded episode.

## Sources

Pattern 1: [Cedar/Lean use case](https://lean-lang.org/use-cases/cedar/) ·
[Cedar OOPSLA'24](https://dl.acm.org/doi/10.1145/3649835) ·
[verification-guided development (FSE'24)](https://arxiv.org/pdf/2407.01688) ·
[Cedar Analysis](https://aws.amazon.com/blogs/opensource/introducing-cedar-analysis-open-source-tools-for-verifying-authorization-policies/) ·
[SymCert (FMCAD'26)](https://www.amazon.science/publications/symcert-verifying-smt-based-policy-analyses) ·
[AgentCore Policy](https://aws.amazon.com/blogs/security/why-policy-in-amazon-bedrock-agentcore-chose-cedar-for-securing-agentic-workflows/) ·
[Bedrock AR checks GA](https://aws.amazon.com/blogs/aws/minimize-ai-hallucinations-and-deliver-up-to-99-verification-accuracy-with-automated-reasoning-checks-now-available/) ·
[AR policy refinement](https://aws.amazon.com/blogs/machine-learning/automated-reasoning-policy-refinement-in-amazon-bedrock/) ·
[3DGen (ICSE'25)](https://arxiv.org/abs/2404.10362) ·
[CodeLogician](https://arxiv.org/abs/2601.11840) ·
[Event-B Agent (FSE'26)](https://arxiv.org/pdf/2605.17475) ·
[ClearSy 25 years of B](https://arxiv.org/pdf/2005.07190)

Pattern 2: [AWS verified authz (ICSE'25)](https://www.amazon.science/publications/formally-verified-cloud-scale-authorization) ·
[vericoding benchmark](https://arxiv.org/abs/2509.22908) ·
[DafnyPro](https://arxiv.org/abs/2601.05385) ·
[AxDafny](https://arxiv.org/html/2606.32007v1) ·
[ATLAS](https://arxiv.org/abs/2512.10173) ·
[AWS Encryption SDK (Dafny)](https://github.com/aws/aws-encryption-sdk) ·
[Dafny Rust backend](https://github.com/dafny-lang/dafny/issues/5561)

Pattern 3: [VeruSAGE](https://arxiv.org/abs/2512.18436) ·
[AutoVerus](https://arxiv.org/abs/2409.13082) ·
[AlphaVerus](https://arxiv.org/abs/2412.06176) ·
[VeruSyn](https://arxiv.org/abs/2602.04910) ·
[Anvil (OSDI'24)](https://www.usenix.org/conference/osdi24/presentation/sun-xudong) ·
[Kani contracts](https://model-checking.github.io/kani/reference/experimental/contracts.html) ·
[verify-rust-std lessons](https://arxiv.org/html/2510.01072v3) ·
[Flux](https://arxiv.org/abs/2207.04034) ·
[Gobra/SCION (CCS'25)](https://arxiv.org/html/2405.06074) ·
[CrossHair AGENTS.md](https://github.com/pschanely/CrossHair/blob/main/AGENTS.md) ·
[SpecPylot](https://arxiv.org/pdf/2604.16560)

Spec-faithfulness & meta: [Clover](https://arxiv.org/abs/2310.17807) ·
[CLEVER](https://arxiv.org/pdf/2505.13938) ·
[Verus-SpecGym](https://arxiv.org/abs/2605.26457) ·
[VeriBench](https://cs.stanford.edu/people/brando9/veribench/blog/veribench-launch/) ·
[Kleppmann prediction](https://martin.kleppmann.com/2025/12/08/ai-formal-verification.html)
([HN](https://news.ycombinator.com/item?id=46203508), [Congdon](https://benjamincongdon.me/blog/2025/12/12/The-Coming-Need-for-Formal-Specification/))

Pattern 5 & gaps: [invariant confluence](https://arxiv.org/abs/1402.2237) ·
[Postgres constraint limits](https://www.postgresql.org/docs/current/ddl-constraints.html) ·
[constraint-trigger pitfalls](https://www.cybertec-postgresql.com/en/triggers-to-enforce-constraints/) ·
[VeriEQL (OOPSLA'24)](https://arxiv.org/abs/2403.03193) ·
[SpotIt (ICLR'26)](https://arxiv.org/abs/2510.26840) ·
[Schemathesis](https://schemathesis.readthedocs.io/) ·
[P/PObserve context (CACM'25)](https://dl.acm.org/doi/10.1145/3729175)

## Open questions

1. Where exactly is the DSL frontier? Cedar covers authz; billing state
   machines and quota/entitlement logic look DSL-able (Imandra suggests
   yes for decision logic); migrations clearly are not. Is there a
   principled test for "this subdomain deserves a verified DSL vs a
   proven kernel"?
2. Does the AgentCore-style NL→Cedar loop hit the same ~⅓–½ vs ~86%
   translation-fidelity spread we saw for F\* vs Dafny? AWS publishes no
   numbers ("significantly improves" only) — R1 would give us our own.
3. Spec faithfulness at the kernel level: VeriBench says stating the right
   theorem is the bottleneck. Our mitigation is the frozen YAML→ensures
   mapping plus human grounding review — can the CLEVER trick (prove
   equivalence to a hidden reference spec) be adapted as a second,
   mechanical check on that mapping?
4. When Dafny's Rust backend lands, does track D's Go embedding migrate
   into the axum process — and does that change the boundary story
   (pattern 4 tokens minted by in-process proven code)?
5. Is VeriEQL's bounded SQL-equivalence check strong enough to gate
   agent-proposed ORM/query refactors in P5, or does the bound reopen the
   sampling-vs-proof gap note 10 exists to close?
