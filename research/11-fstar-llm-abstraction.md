# F* as the rule language for an LLM-driven workflow?

**Date, status:** 2026-08-06, draft (desk research; hands-on parked — see
"Environment feasibility"). Context per CLAUDE.md: we evaluate for a
**regular web SaaS application**, not kernels/crypto.

Refines the F* row of [03-code-level-verification.md](03-code-level-verification.md)
("Low–Medium LLM-friendly, not for operational code") with a deeper dive,
because F* is the one language where *the type IS the rule*: if
"rules as a higher level of abstraction" has a purist endpoint, it is
dependent/refinement types checked by SMT. The question is whether that
endpoint is reachable by LLM agents for SaaS code today.

## TL;DR / verdict

- **Not as the primary rule language for a web SaaS app.** The extraction
  targets (OCaml, F#, C via Karamel, Rust via Pulse) miss mainstream SaaS
  stacks; there is no web-framework, SQL, or ORM story; CI proof replay is
  slow and Z3-flaky; and F* specs (dependent types + separation logic) are
  the hardest artifacts in our survey for a *human* to ground-review —
  which violates our translate/validate split at the human end
  (guardrail 5).
- **LLM evidence is real but a tier below Dafny.** Microsoft's own
  benchmark (FStarDataSet, ~32K–54K definition-level problems from
  production F* code) shows LLMs + type-based retrieval automate roughly
  **a third to a half of proofs**; fine-tuned small models (Phi-2,
  StarCoder) match GPT-4-class models. Compare Dafny: DafnyPro 86%
  (note 03), vericoding benchmark 82% Dafny vs 44% Verus vs 27% Lean —
  **F* is absent from the 2026 vericoding benchmark entirely**, a signal
  of thin training data and community mass relative to Dafny.
- **Two things are worth stealing.**
  1. **The 3DGen pattern**: LLM agents write in a *constrained DSL* (3D
     for binary formats); a verified F* toolchain (EverParse) compiles the
     DSL to provably safe code; symbolic test generation feeds the agent
     counterexamples. The LLM never touches proof obligations — the DSL
     limits its output to a class where verification is automatic. That is
     our translate/validate split (guardrail 5) plus counterexample
     currency (guardrail 6) plus boundaries-by-construction (guardrail 8),
     shipped by Microsoft. The transferable move for SaaS: a small DSL for
     one subdomain (authz rules, billing state machines, API schemas) with
     a *pre-verified* interpreter/compiler — the per-feature agent loop
     then needs no prover at all.
  2. **Effects/indexed types as by-construction boundaries**: F* can state
     "this handler is pure / never diverges / can only touch the DB
     through this capability" *in the type*, strictly stronger than our
     Grant<Op> token trick (track G). If we ever need a richer kernel
     boundary than Dafny+Rust gives us, F*/Pulse is where it exists today.
- **Position on the escalation ladder (note 10):** F* sits at the top —
  code-level proofs at any depth/size, and relational (hyperproperty)
  reasoning is expressible. But cost-per-obligation is the highest in the
  survey, and for our purposes the model-level tools (Quint/Apalache,
  mypyvy, TLC) already cover tiers 1–4 at a fraction of the cost.

## What F* is (2026 snapshot)

- Proof-oriented dependently typed ML-family language; proofs discharged
  by Z3 (pinned version; the binary ships its own) plus tactics (Meta-F*).
  Active: releases v2026.06.14, v2026.06.21; installable from GitHub
  binaries or opam (builds from source).
- **Pulse**: an embedded DSL for imperative/concurrent code in a modern
  concurrent separation logic (PulseCore, 2025: impredicative invariants,
  higher-order ghost state, later credits), foundationally justified
  inside F* itself. Evaluation spans **31K+ lines of verified code**;
  flagship 2025 result: verified CBOR/CDDL/COSE parsers & serializers
  (CCS 2025), extracted to C and Rust.
- Proven at production scale via Project Everest: HACL* crypto (shipped in
  Windows, Linux kernel, Firefox, Python), EverParse (verified zero-copy
  parsers, used for Windows kernel components), miTLS.
- Extraction: OCaml/F# (default), C (Low*/Karamel), Rust (from Pulse),
  WebAssembly, assembly (Vale). "Verify in F*, run as C/OCaml/Rust."

## The case FOR (why it tempts us)

1. **Spec and code are one artifact.** A refinement type
   `xs:list order{total xs <= credit_limit}` is the invariant, the
   documentation, and the gate — no model↔code boundary to test
   (the boundary our tracks B/C/N spend all their effort on *disappears*
   for whatever lives inside F*).
2. **SMT-backed automation, not interactive proving.** Unlike Lean/Rocq,
   the default mode is Dafny-like: write the type, Z3 does the proof. The
   tactic escape hatch exists but much production F* never uses it.
3. **The strongest by-construction story in the survey** (guardrail 8):
   effects, indexed monads, typestate — a compile error, not a lint, for
   "handler read the DB without a tenant capability".
4. **Real LLM research exists on real code**: FStarDataSet is the largest
   corpus of SMT-assisted proofs anywhere (600K–940K lines, from shipped
   systems), with a reproducible fragment-level checker — i.e. the
   verifier-gated loop we use everywhere is already packaged for F*.
5. **3DGen shows the agentic endgame** on F* infrastructure: informal RFC
   prose + examples → agents → 3D DSL spec → provably correct parser in C,
   evaluated on 20 Internet formats. Nobody has shown this for Dafny.

## The case AGAINST (for a web SaaS)

1. **Stack mismatch.** Our app tier is ordinary web code (P3 is Rust/axum
   + Postgres). F* extracts to OCaml/C/Rust-via-Pulse; there is no
   HTTP/SQL/framework ecosystem. F* could only ever be the *kernel*
   language (like Dafny in tracks D/G/L) — and as a kernel prover for LLM
   loops, Dafny currently wins on every LLM metric we found.
2. **LLM success rate ~⅓–½ vs Dafny's ~86%.** With guardrail 3 ("weaker
   models are fine when the gate is strong") we care less about raw rates —
   but rate still sets loop cost, and a 2–3× gap is a 2–3× gap.
3. **Counterexample currency is weak** (guardrail 6). A failed Z3
   obligation in F* is a timeout or an opaque "could not prove
   post-condition", not an ITF-trace or a named 403. (The community wiki
   page is literally titled "Getting better mileage out of Z3".) Quantifier
   instability means proofs can break on unrelated edits — poison for a
   frozen-gate design where red must mean *the agent's edit is wrong*.
4. **Human review burden** (guardrail 5). Sentence-by-sentence grounding
   of a dependent type with ghost state and separation-logic assertions is
   specialist work; our Quint/TLA+ specs are readable by a careful
   generalist.
5. **Benchmark absence compounds.** F* missing from the POPL 2026
   vericoding benchmark (3,029 Dafny / 2,334 Verus / 7,141 Lean specs, 0
   F*) means less training data, fewer eval-driven tooling improvements,
   and no third-party number to falsify vendor claims with.

## Environment feasibility (this repo)

- GitHub release binaries: **blocked** (proxy 403 on github.com,
  confirmed 2026-08-06). No opam/OCaml toolchain preinstalled.
- Plausible path: `apt install opam` (candidate 2.1.5 available) →
  `opam init` → `opam install fstar` — opam.ocaml.org and its source-tarball
  cache are reachable (200). Untested; expect a long source build
  (F* + Z3 + OCaml deps). Same class of workaround as mypyvy-via-git-clone.

## Falsifiable predictions (scoreboard candidates)

| # | Prediction | Falsifier |
|---|-----------|-----------|
| F1 | `opam install fstar` succeeds in this container via the opam cache | build fails on a github.com fetch |
| F2 | Porting the authorization kernel (track G/L) to F* takes an LLM agent ≥3× the repair rounds Dafny took, using the same gate | ≤ Dafny's rounds |
| F3 | A 3DGen-style loop (agent writes a tenant-isolation DSL, pre-verified checker compiles it) needs **zero** prover calls per feature and beats the P4 gate on round count | prover needed per-feature, or more rounds |

## Prototype ideas (only if F1 passes)

1. **P-F\*1 — kernel port shootout:** same authorization kernel, same
   frozen gate, same generic prompt (the P4 episode-2 method): Dafny vs
   F*. Measures F2 directly; also measures proof-replay time in CI.
2. **P-F\*2 — steal-the-pattern without F\*:** build the tenant-isolation
   DSL + verified-once checker in *our existing stack* (Quint/Z3 checker
   from P2 as the "verified" core). Tests whether the 3DGen shape — DSL
   surface for the LLM, no per-feature proofs — is the real win,
   independent of F* itself. This one is doable today.

## Sources

- [F* homepage](https://fstar-lang.org/) ·
  [F* releases (v2026.06.x)](https://github.com/fstarlang/fstar/releases) ·
  [INSTALL.md](https://github.com/FStarLang/FStar/blob/master/INSTALL.md) ·
  [Wikipedia: F*](https://en.wikipedia.org/wiki/F*_(programming_language))
- [Pulse tutorial chapter](https://fstar-lang.org/tutorial/book/pulse/pulse.html) ·
  [PulseCore paper, 2025](https://fstar-lang.org/papers/pulsecore-indirection-2025.pdf) ·
  [PulseCore (MSR)](https://www.microsoft.com/en-us/research/publication/pulsecore-an-impredicative-concurrent-separation-logic-for-dependently-typed-programs/)
- [Towards Neural Synthesis for SMT-Assisted Proof-Oriented Programming
  (arXiv 2405.01787)](https://arxiv.org/abs/2405.01787) — FStarDataSet,
  "a third to a half of proofs" ·
  [MSR page](https://www.microsoft.com/en-us/research/publication/towards-neural-synthesis-for-smt-assisted-proof-oriented-programming/) ·
  [slides](https://pnwplse.org/slides/2024/Gabriel%20Ebner.pdf)
- [3DGen: AI-Assisted Generation of Provably Correct Binary Format Parsers
  (arXiv 2404.10362)](https://arxiv.org/abs/2404.10362) ·
  [EverParse](http://www.normalesup.org/~ramanana/research/everparse/)
- [A benchmark for vericoding (Dafny @ POPL 2026)](https://popl26.sigplan.org/details/dafny-2026-papers/13/A-benchmark-for-vericoding-formally-verified-program-synthesis) ·
  [OpenReview](https://openreview.net/forum?id=Zgh5kpGAm8) — 82% Dafny /
  44% Verus / 27% Lean, no F* track
- [Getting better mileage out of Z3 (F* wiki)](https://github.com/FStarLang/FStar/wiki/Getting-better-mileage-out-of-Z3)
- [Kleppmann: AI will make formal verification go mainstream (Dec 2025)](https://martin.kleppmann.com/2025/12/08/ai-formal-verification.html)

## Open questions

1. Does the FStarDataSet ⅓–½ rate improve materially with a
   verifier-gated repair loop (their number is largely single-shot +
   retrieval)? Nobody has published the F* analogue of DafnyPro.
2. Pulse→Rust extraction maturity: could a verified Pulse kernel slot into
   the P3 axum app the way Dafny→Go did in track D? (Would make F2
   testable end-to-end.)
3. Is proof instability (Z3 quantifier flakiness) actually worse than
   Dafny's in practice, or just worse-documented? Needs the F1/F2
   prototype to measure re-verification determinism across whitespace-level
   edits.
