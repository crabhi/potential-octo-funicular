# LLMs x formal methods

Date: 2026-07-30. Status: draft.

## TL;DR

- **NL -> formal spec translation is the weakest link, not code generation.** Across
  several 2025/2026 benchmarks, the same models that hit 85-92% on plain code
  generation drop to single digits or low tens-of-percent on nl2spec-style tasks
  (TLA+, Alloy, general spec languages). Model size doesn't predict quality;
  reasoning/prompting strategy matters more than parameter count.
- **LLM-assisted deductive verification (Dafny/Verus) is the most mature
  practical pattern.** Verifier-gated loops (generate -> check -> feed error
  back -> regenerate) reliably push success rates up (DafnyBench: ~68% best
  reported single-shot-with-retry; DafnyPro claims 86% with Claude 3.5 Sonnet;
  AlphaVerus/Verus work shows tree-search + verifier feedback beats greedy
  sampling by a wide margin).
- **Industrial deployment exists today for a *restricted*, non-Turing-complete
  rule language**, not for general spec languages: AWS Bedrock "Automated
  Reasoning checks" (GA Aug 2025) uses an SMT-LIB subset with a hard
  separation between (a) LLM-driven NL->logic *translation* (unsound, scored
  by cross-model agreement) and (b) SMT-based *validation* (sound). This
  translate/validate split is the single most transferable industrial idea.
- **Counterexample-guided repair (CEGIS-with-LLM-as-synthesizer) is a proven
  loop shape** across proof repair (Baldur), program repair (LLM-CEGIS-Repair,
  MENTOR), and verified transpilation — the LLM proposes, a checker returns
  a concrete counterexample, the LLM repairs. This generalizes directly to
  the project's "verifier gates the agent's edits" milestone.
- **GitHub SpecKit and most "spec-driven development" agent tooling are
  informal** — specs there are structured Markdown/prose, not machine-checked
  formal artifacts. No mainstream agent-loop tool today gates edits on a
  formal model checker/theorem prover by default; that gap is exactly what
  this project is aiming to fill.
- **Common failure modes are well characterized**: hallucinated
  syntax/library APIs, vacuous or under/over-constrained specs that vacuously
  pass, and specs that are locally plausible but don't match developer
  intent (spec-level bugs a verifier can't catch). Mitigations in the
  literature: syntax-checking/parser-in-the-loop retries, multi-model
  translation-agreement scoring, human review UIs anchored to source text
  ("fidelity reports"), and negative-test/vacuity checks.

## Landscape

### NL -> spec translation

- **TLA+**: A 2026 ICSOFT-accepted study ("Can LLMs Write Correct TLA+
  Specifications?", arXiv 2606.05792) ran 30 LLMs (25 open-weight x 4
  prompting strategies = 2,600 runs, plus 5 proprietary models few-shot) over
  205 hand-curated specs, validated by SANY (parser) + TLC (model checker).
  Results: **26.6% syntactic correctness, only 8.6% semantic correctness**;
  semantic success occurred almost exclusively under a "progressive
  prompting" strategy (build the spec incrementally with checker feedback
  between steps), not direct or few-shot prompting. Notably, DeepSeek
  r1:8b beat its own 70B variant, and general code-strong models showed
  *negative* transfer onto TLA+ — training on Python/Java doesn't help and
  can hurt. `tlaplus/TLAiBench` on GitHub is an emerging benchmark/dataset
  for this.
- **Alloy / general specs (SpecGen-style benchmarks)**: A recent
  benchmark (referenced as "VeriContest"-style nl2spec eval, mid-2026) shows
  the code-vs-spec gap starkly: GPT-5.5 92.18% nl2code -> 48.31% nl2spec;
  Claude Opus 4.7 90.17% -> 20.82%; Gemini 3.1 Pro 88.79% -> 19.03%; open
  models fall off a cliff (Qwen3.6: 77.91% -> 0.32%). Strong nl2code ability
  correlates loosely with nl2spec ability but is not sufficient. Separately,
  SpecGen (ICSE 2025, arXiv 2401.08807) generates Java/C specs via
  mutation + LLM-repair loop and gets 279/385 programs to a verifiable spec,
  beating Houdini/Daikon-style tools — but that's specs-for-verification, a
  narrower and more tractable task than general property specs.
- **LTL / requirements**: Req2LTL and hierarchical-decomposition approaches
  (arXiv 2512.17334) report much higher numbers (88.4% semantic accuracy,
  100% syntactic) on LTL translation for aerospace-style requirements — LTL's
  small, regular grammar and closer proximity to natural "always/eventually/
  until" phrasing seems to make it more LLM-tractable than TLA+ or Alloy.

### LLM-assisted proofs / annotations (deductive verification)

- **Dafny** is the best-supported target because it's auto-active
  (SMT-backed, single-file, decent error messages back to the model).
  - DafnyBench (POPL 2025 workshop): 750+ programs, ~53K LOC; best
    model+prompting got **68%** success, improved further with
    retry-on-verifier-error loops.
  - dafny-annotator (Dafny blog, June 2025): combines LLM + search to insert
    annotations until the verifier accepts. Greedy search with LLaMA-3.1-8B
    got only 15.7% on the DafnyBench test set; **fine-tuning** the 8B model
    on DafnyBench+DafnySynth data raised it to 50.6% — fine-tuning on
    verifier-checked data matters more than model scale here.
  - DafnyPro (arXiv 2601.05385) reports 86% correct proofs on DafnyBench
    with Claude 3.5 Sonnet, +16pp over prior SOTA, via better
    verifier-feedback loop design.
  - Clover (arXiv 2310.17807 / ESOP-adjacent workshop) generates
    code+Dafny-annotation+docstring together and cross-checks all three for
    *consistency* rather than trusting any one of them; up to 87% acceptance
    on correct examples with ~0 tolerance for adversarial-incorrect ones on
    the small hand-built CloverBench. Key idea: consistency-checking across
    redundant artifacts is a cheap way to catch a spec that's technically
    valid but doesn't match the docstring/intent.
  - Re:Form and RL-with-negative-tests papers (2025-2026) are pushing toward
    training models specifically on formal-spec-synthesis reward signals
    rather than relying on prompting alone — an emerging trend, not yet
    productized.
- **Verus (Rust)**: AlphaVerus (arXiv 2412.06176) bootstraps verified Rust
  by translating from Dafny -> Verus with verifier feedback across
  Exploration/Treefinement/Critique stages, self-improving without a
  frontier-model bootstrap. Follow-on work (VeruSyn, KVerus, "Reducing the
  Costs of Proof Synthesis on Rust Systems") is scaling seed data and
  context-chunking strategies through 2026. AWS's KaPilot (arXiv 2607.21957)
  is a multi-agent system generating Kani-style specs/contracts for *unsafe*
  Rust memory safety — notable because it's explicitly checker-gated: "some
  AI-generated contracts required correction, though all were caught by
  Kani rather than human review," i.e., the model checker is treated as the
  safety net, not the human.
- **Baldur (ESEC/FSE 2023, arXiv 2303.04910)** is the foundational
  counterexample-repair result: whole-proof generation for Isabelle/HOL,
  then a *separate fine-tuned repair model* takes (failed proof, error
  message) and fixes it. Combined with Thor, provers close 65.7% of a
  6,336-theorem benchmark. This "generate once, repair with error context"
  pattern recurs everywhere below.

### Verifier-gated agent loops

- **CEGIS-with-LLM pattern**: LLM-CEGIS-Repair (AAAI 2025) uses an LLM as
  the synthesizer inside a classic counterexample-guided inductive synthesis
  loop for program repair, combined with MaxSAT fault localization to narrow
  where to edit before asking the LLM to patch. MENTOR applies the same
  loop shape to introductory-programming repair. Verified-transpilation work
  (LLMLift, NeurIPS 2024) frames LLM-based code lifting explicitly as CEGIS:
  synthesizer proposes, verifier returns a concrete counterexample on
  failure, repeat. This is the most directly reusable loop shape for the
  project's M4 (agent optimizes code, verifier gates edits, counterexamples
  drive retries).
- **Spec-driven development tooling (informal)**: GitHub Spec Kit
  (released Sept 2025, github/spec-kit) structures agent workflows as
  `/speckit.specify -> /speckit.plan -> /speckit.tasks -> /speckit.implement`
  with Markdown specs as the "source of truth." It is explicitly **not**
  formally checked — the spec is a structured prose contract that guides
  prompting, not something an SMT solver or model checker validates. It's
  useful as a UX/workflow reference (how to structure a spec-first agent
  loop) but contributes nothing on the "gate edits with a formal verifier"
  requirement. We found no mainstream agent-loop product that plugs a model
  checker or theorem prover into the loop as a hard gate by default; that
  remains a research-tool pattern (Dafny/Verus loops above) rather than a
  packaged agent product.
- **CURRANTE** (VS Code extension) is a lighter human-in-the-loop pattern:
  Specification -> Tests -> Function stages, letting a developer review/edit
  at each stage rather than fully automating — relevant as a UI reference
  even though its "specification" stage is not formal.

### Industrial deployments

- **AWS Bedrock Automated Reasoning checks** (preview Dec 2024, GA Aug
  2025, extended with NL test-Q&A generation Nov 2025) is the clearest
  production deployment of "LLM + formal verification" at scale, and its
  design is directly relevant to this project's M1-M3:
  - A **policy** = formal logic rules (if-then implications) + a typed
    variable schema (BOOL/INT/NUMBER/enum) + custom types, expressed in a
    **subset of SMT-LIB**. Policies are authored by extracting rules from
    natural-language source documents (handbooks, specs) via LLM, then
    reviewed by a human against a **fidelity report** — a coverage score,
    an accuracy score, and per-rule/per-variable grounding back to specific
    source sentences. This is a genuinely good pattern for developer review
    of LLM-authored formal artifacts without requiring the reviewer to read
    raw SMT-LIB.
  - Runtime validation is explicitly two-phase: (1) **translate** — LLM(s)
    map an NL claim into formal premises/claims against the policy's
    variables (unsound, scored by *cross-model agreement* = confidence);
    (2) **validate** — SMT solver checks the translated logic against the
    rules (sound). AWS is explicit that when something goes wrong, "the
    issue is most likely in translation, not validation" — the solver step
    is trusted, the NL-mapping step is not.
  - Result taxonomy is richer than pass/fail: `VALID`, `INVALID`,
    `SATISFIABLE` (true under some but not all completions — i.e. an
    underspecified answer), `IMPOSSIBLE` (input or policy is self-contradictory
    — this is the "query for contradictions" capability the project brief
    wants), `TRANSLATION_AMBIGUOUS` (models disagreed on meaning), `TOO_COMPLEX`,
    `NO_TRANSLATIONS`. Bare (non-implicative) rules are flagged as a known
    footgun because they become axioms and can silently make a legitimate
    input `IMPOSSIBLE`.
  - Deliberately restricted expressiveness (BOOL/INT/NUMBER/enum, no raw
    strings, no computed values) so translation stays tractable — an
    explicit design trade-off, not an oversight.
- **AWS Cedar** (authorization policy language): formally modeled in Lean,
  proofs of safety/security properties, cross-checked by differential
  testing against the Rust implementation (arXiv 2407.01688,
  lean-lang.org Cedar case study). Not itself LLM-authored, but the
  Lean-model + differential-testing pattern is a template for "keep a
  lightweight formal model in lockstep with the real implementation."
- **AWS Kani**: bounded model checker for Rust; used both directly by AWS
  teams (e.g., found a real bug in Cedar's evaluator) and as the target for
  LLM-assisted spec generation (KaPilot, above).
- **Anthropic / OpenAI**: no found evidence of published formal-methods
  research groups comparable to AWS's; the visible signal is instead
  "verification via testing/agentic scale" (Anthropic reports Claude
  authoring 80%+ of its own merged production code by mid-2026, and
  large-scale agentic builds like a full C compiler) rather than SMT/proof-
  based verification. Industry commentary (AI Engineer World's Fair 2026)
  notes the field's center of gravity shifting "from generation to
  verification" in 2026, but concretely-published verification work in this
  space is coming from AWS, academia, and Dafny/Verus/Lean communities, not
  from model vendors themselves. Treat "no vendor-side formal-methods
  moat" as current-state, worth rechecking in 6-12 months.

## What works today vs. research-only

**Works today, can build on directly:**
- Verifier-in-the-loop retry for Dafny/Verus: generate -> run verifier ->
  feed the actual error/counterexample back -> regenerate. Consistently
  the single biggest lever across every benchmark above (DafnyBench,
  dafny-annotator, DafnyPro, AlphaVerus, KaPilot).
- Restricted, typed rule languages (SMT-LIB subset, small typed variable
  schema) for LLM-authored formal content. Full expressive general-purpose
  spec languages (TLA+, Alloy) are still poorly handled; small,
  implication-shaped, boolean/arithmetic rule sets are handled well.
  AWS's production numbers ("up to 99% accuracy detecting correct
  responses") back this — but note that's on a deliberately narrow,
  non-Turing-complete logic, not general TLA+/Alloy specs.
- Fidelity/grounding reports (rule <-> source-sentence traceability + a
  scalar accuracy/coverage score) as a spec-review UI pattern usable by a
  non-formal-methods developer.
- CEGIS-style repair loops (counterexample in, patch out) for both proofs
  (Baldur) and code (LLM-CEGIS-Repair, MENTOR, LLMLift) — proven, reusable
  loop shape, not just a research curiosity.

**Research-only / fragile, don't rely on yet:**
- Direct NL -> TLA+/Alloy translation without heavy scaffolding: single-digit
  to ~25% success rates even from frontier models; "progressive prompting"
  (checker-in-the-loop, incremental construction) is required to get above
  single digits, and even then only ~8.6% full semantic correctness on the
  TLA+ benchmark.
- Fully autonomous spec authoring with no human review: every credible
  source (AWS docs, the "unalarming" practitioner writeup, the AlphaVerus/
  Clover papers) treats human review of the spec — not just the code — as
  necessary, because a verifier can prove code matches a spec but cannot by
  itself tell you the spec matches developer intent (the "spec-level bug"
  problem, i.e. vacuous or wrong specs that verify cleanly).
  design-partner note: this is precisely why the project brief puts
  "developer reviews" as step 2 of the workflow — that instinct is
  corroborated across sources, not just prudent caution.
- General agent products with formal-verifier gating baked in: doesn't
  exist as a shipped product; SpecKit-style tools are informal. This is a
  build-it-yourself gap, matching M3/M4 of the brief.
- Dynamic/reflective/highly polymorphic code in Dafny-style auto-active
  languages: explicitly called out as a weak spot — matters if the target
  web app's implementation language leans on dynamic features.

## Design implications for our pipeline

1. **Split "translate" from "validate" like AWS does, everywhere in the
   pipeline** — not just for the runtime checks but for the *initial*
   NL-invariant -> formal-spec step too. Treat the LLM's NL->spec mapping as
   unsound-by-construction (score it, don't trust it), and treat whatever
   solver/model-checker validates it downstream as the sound half. This
   maps cleanly onto brief step 2-3 (translate + query for contradictions).
2. **Prefer a small, typed, implication-shaped rule schema over a full
   general-purpose spec language for the parts of the model an LLM must
   author directly.** Given TLA+/Alloy's poor NL-authoring track record,
   consider a layered approach: (a) developer invariants first pass through
   a *restricted* typed schema (booleans/ints/enums/implications, à la
   Bedrock's Automated Reasoning policies) that an LLM can translate into
   reliably and a human can review sentence-by-sentence via a fidelity-style
   report; (b) only compile/lower that restricted layer into TLA+/Alloy/
   whatever full model-checker language is chosen for the heavier
   concurrency reasoning (see notes 01, 04), rather than asking the LLM to
   author the full-power language directly. This directly serves the
   project's need to query for contradictions pre-code (Bedrock's
   `IMPOSSIBLE`/`SATISFIABLE`/`TRANSLATION_AMBIGUOUS` taxonomy is a good
   template for what "query for contradictions" should return, not just a
   yes/no).
3. **For code-level verification, budget for Dafny-shaped auto-active
   proof if the chosen implementation language allows it** (or Verus if
   Rust is chosen per the brief's language list) — this is the
   best-evidenced LLM+FM combination today, especially with a
   verifier-in-the-loop retry budget of a few rounds (diminishing but real
   returns reported up to several retries in DafnyBench/DafnyPro).
4. **Build the counterexample-feedback contract early and treat it as a
   first-class interface**, since it's reused at every layer: model-checker
   counterexample -> spec repair (TLA+/Alloy stage), verifier
   error/counterexample -> proof-annotation repair (Dafny/Verus stage), and
   runtime-trace violation -> code repair (agent optimization stage,
   milestone M4). Baldur/CEGIS work shows repair-with-context clearly beats
   generate-from-scratch; the same "counterexample + prior attempt + rule
   citation" payload shape should flow through all three.
5. **Spec review UI should show grounding, not raw formal syntax as the
   primary view.** Borrow AWS's fidelity-report idea directly: for every
   rule/invariant, show (a) the source NL sentence(s) it came from, (b) a
   confidence/agreement score if multiple LLM translations were sampled,
   (c) a concrete "true scenario" and, where relevant, a "false scenario" —
   i.e. surface `SATISFIABLE`-style ambiguity as two side-by-side example
   states, not as an abstract logic formula. Developers reviewing invariants
   (brief step 2) should not need to read the formal language fluently.
6. **Explicitly test for vacuous/underconstrained specs before trusting a
   "verified" result.** Add a standard check (does the spec accept an
   intentionally-broken negative example? does removing a conjunct change
   provability?) as a gate before a spec is marked developer-approved —
   several sources flag vacuous/over- or under-constrained specs as a
   silent, verifier-invisible failure mode.

## Prototype ideas (1-2 day scale)

- **P1 — Translate/validate split demo, no AWS dependency**: Take 5-10 of
  the project's own candidate invariants (informal, in English). Hand-roll
  a tiny typed variable schema + SMT-LIB implication rules by hand (to
  isolate the "does the split help" question from "can the LLM author
  SMT-LIB well"), then have an LLM translate a batch of NL claims/scenarios
  against that schema into premises/claims, and run them through a solver
  (z3 directly, or python z3 bindings) to reproduce AWS's VALID/INVALID/
  SATISFIABLE/IMPOSSIBLE taxonomy locally. Goal: validate the taxonomy is
  useful for surfacing contradictions in *our* invariant set before writing
  any TLA+.
- **P2 — Progressive-prompting TLA+ mini-benchmark**: Pick 3-5 invariants
  from the project's own domain (API + DB migration model), have an LLM
  produce a TLA+ spec three ways — direct prompt, few-shot, and
  "progressive" (spec skeleton -> SANY parse -> fix -> TLC check small
  config -> fix) — and record syntactic/semantic pass rates. Cheap way to
  confirm the 8.6%-style semantic-success number generalizes (or doesn't)
  to our own spec style, and to decide whether the pipeline needs a
  progressive-prompting harness by default.
- **P3 — Dafny verifier-loop micro-prototype**: Take one narrow, already-
  understood function from the target web API (e.g., an idempotency-key
  check or a counter increment) and have an LLM (a) write it in Dafny with
  contracts, (b) iterate against `dafny verify` errors for up to 5 rounds.
  Measure how many rounds to converge, and whether Claude-family models
  show the same convergence speed reported for DafnyPro/DafnyBench. This is
  the cheapest way to validate assumption 3 above using our actual model
  access before committing to Dafny/Verus for M3.
- **P4 — Counterexample-repair harness skeleton**: A tiny CLI:
  `run_checker(spec) -> {ok, counterexample}` , then a loop that feeds
  `counterexample + previous spec/code + one-line rule citation` back to
  the LLM for at most N retries, logging convergence. Implement against
  whatever checker note 01/03 recommends; this is the reusable scaffold
  referenced in design implication #4 and should be built once, generically,
  rather than per-layer.
- **P5 — Vacuity/negative-test gate**: For any spec produced in P1/P2,
  auto-generate one deliberately-violating scenario per invariant and
  confirm the checker rejects it (catches vacuous "always true" specs) —
  small, mechanical, and directly targets the "vacuous spec" failure mode.

## Sources

- [Can LLMs Write Correct TLA+ Specifications? Evaluating Natural-Language-to-TLA+ Generation (arXiv 2606.05792)](https://arxiv.org/abs/2606.05792)
- [AI4FM: Can LLMs Write Correct TLA+ Specifications?](https://ai4fm.cs.luc.edu/papers/llm-tla-evaluation/)
- [tlaplus/TLAiBench (GitHub)](https://github.com/tlaplus/TLAiBench)
- [Bridging NL and Formal Specification via Hierarchical Semantics Decomposition (LTL) (arXiv 2512.17334)](https://arxiv.org/html/2512.17334v1)
- [SpecGen: Automated Generation of Formal Program Specifications via LLMs (ICSE 2025 / arXiv 2401.08807)](https://arxiv.org/pdf/2401.08807)
- [KBSpec: LLM-driven Formal Specification Generation with Evolving Domain Knowledge Base (arXiv 2606.21339)](https://arxiv.org/pdf/2606.21339)
- [VeriAct: Agentic Synthesis of Correct and Complete Formal Specifications (arXiv 2604.00280)](https://arxiv.org/pdf/2604.00280)
- [DafnyBench: A Benchmark for Formal Software Verification (POPL 2025 Dafny workshop)](https://popl25.sigplan.org/details/dafny-2025-papers/15/DafnyBench-A-Benchmark-for-Formal-Software-Verification)
- [dafny-annotator: AI-Assisted Verification for Dafny (Dafny blog, June 2025)](https://dafny.org/blog/2025/06/21/dafny-annotator/)
- [DafnyPro: LLM-Assisted Automated Verification for Dafny Programs (arXiv 2601.05385)](https://arxiv.org/html/2601.05385)
- [Re:Form: Reducing Human Annotations in Scalable Formal Verification with RL in LLMs (arXiv 2507.16331)](https://arxiv.org/pdf/2507.16331)
- [Clover: Closed-Loop Verifiable Code Generation (arXiv 2310.17807)](https://arxiv.org/abs/2310.17807)
- [AlphaVerus: Bootstrapping Formally Verified Code Generation (arXiv 2412.06176)](https://arxiv.org/pdf/2412.06176)
- [KaPilot: LLM-Assisted Generation of Kani Specifications for Unsafe Rust (arXiv 2607.21957)](https://arxiv.org/html/2607.21957v1)
- [Baldur: Whole-Proof Generation and Repair with LLMs (arXiv 2303.04910)](https://arxiv.org/abs/2303.04910)
- [LLM-CEGIS-Repair: Counterexample Guided Program Repair (AAAI 2025)](https://github.com/pmorvalho/LLM-CEGIS-Repair)
- [MENTOR: Fixing introductory programming assignments (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/pii/S0164121225003590)
- [Verified Code Transpilation with LLMs / LLMLift (NeurIPS 2024)](https://people.eecs.berkeley.edu/~sseshia/pubdir/llmlift-neurips24.pdf)
- [Amazon Bedrock: Automated Reasoning checks concepts](https://docs.aws.amazon.com/bedrock/latest/userguide/automated-reasoning-checks-concepts.html)
- [AWS: Automated Reasoning checks GA announcement](https://aws.amazon.com/about-aws/whats-new/2025/08/automated-reasoning-checks-amazon-bedrock-guardrails)
- [AWS blog: How Automated Reasoning checks transform generative AI compliance](https://aws.amazon.com/blogs/machine-learning/how-automated-reasoning-checks-in-amazon-bedrock-transform-generative-ai-compliance/)
- [How We Built Cedar: A Verification-Guided Approach (arXiv 2407.01688)](https://arxiv.org/pdf/2407.01688)
- [Lean Powers Secure Software at AWS: Cedar's Journey (lean-lang.org)](https://lean-lang.org/use-cases/cedar/)
- [Kani: A Model Checker for Rust (arXiv 2607.01504)](https://arxiv.org/html/2607.01504v1)
- [GitHub Spec Kit (github/spec-kit)](https://github.com/github/spec-kit)
- [GitHub Blog: Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [LLMs and Formal Methods (practitioner writeup, unalarming.com)](https://unalarming.com/llms-and-formal-methods)
- [Leveraging LLMs for Formal Software Requirements: Challenges and Prospects (arXiv 2507.14330)](https://arxiv.org/pdf/2507.14330)
- [VeriContest: A Competitive-Programming Benchmark for Verifiable Code Generation (arXiv 2605.08553)](https://arxiv.org/pdf/2605.08553)
- [Verus-SpecGym: An Agentic Environment for Evaluating Specification Autoformalization (arXiv 2605.26457)](https://arxiv.org/pdf/2605.26457)
- [SpecBench: Evaluating Specification-Level Reasoning for SWE LLM Agents (arXiv 2605.30314)](https://arxiv.org/html/2605.30314)

## Open questions

- Does the AWS "translate vs. validate" split generalize cleanly to a
  concurrency-aware model (multiple in-flight requests + migrations), or
  does it implicitly assume single-shot Q&A-style claims? Needs a check
  against note 05's concurrency model before relying on it for the runtime
  layer.
- How much of the TLA+/Alloy poor-performance result is prompting-strategy
  artifact vs. a real ceiling? "Progressive prompting" was the only strategy
  that worked in the ICSOFT study — is that just "give the model a REPL and
  let it iterate," and if so, does giving Claude/GPT direct SANY/TLC tool
  access (as an agent, not a one-shot prompt) close most of the gap? Worth
  a quick empirical check (P2) rather than trusting the benchmark's
  prompting choices.
- Is there a maintained, LLM-friendly Alloy or TLA+ "linter/formatter" tool
  analogous to Dafny's fast local verifier round-trip? Faster/cheaper
  syntax-checking loops seem to be a bigger lever than model choice per the
  DeepSeek r1:8b result — worth confirming tooling exists for whichever
  spec language note 01 recommends.
- No concrete published data found from Anthropic or OpenAI on
  formal-verification-gated codegen specifically (as opposed to
  test-gated agentic codegen at scale) — is that because it doesn't exist,
  or because it's not public? Worth a targeted follow-up close to decision
  time (M2) rather than assuming absence of evidence is evidence of absence.
- AWS's Automated Reasoning policies cap variable types at
  BOOL/INT/NUMBER/enum and explicitly warn off free-form strings/derived
  values — would the project's invariants (about API requests + DB state)
  fit that restriction, or do they need richer structure (records, sets,
  sequences) that pushes back toward full TLA+/Alloy regardless? This
  bears directly on design implication #2 and should be checked against a
  few real candidate invariants early in M2.
