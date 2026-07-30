# Code-level verification tools

**Date, status:** 2026-07-30, draft

## TL;DR

- **Verus (Rust)** dominates deductive-proof ecosystem; LLM-friendly (VeruSAGE >80% success); best for system code; concurrency via proof (not builtin).
- **Dafny** verification-aware language; strong LLM proof generation (DafnyPro 86% on benchmarks); compiles to multiple targets; good CI speed.
- **Kani (Rust)** bounded model checking; fully automated; handles unsafe; fast for loops/concurrency but limited to finite bounds.
- **Gobra (Go)** modular verifier; targets concurrency (goroutines, channels); good for web API patterns; ETH/industrial use.
- **Java (OpenJML)** actively maintained 2025–2026; slower proofs than others; large legacy codebase support.
- **Python tools** (icontract/CrossHair/deal) lightweight runtime contracts; no static proof; faster but weaker guarantees.

## Inventory

| Tool | Language | Style | Maturity | CI Speed | LLM-Friendly |
|------|----------|-------|----------|----------|--------------|
| Verus | Rust | Deductive proof (SMT-based) | High (2025–2026 industrial) | Slow (5–20 min per module) | **Excellent** (>80% proof synthesis) |
| Dafny | Any (compiles to C#, Java, Go, Rust, Python) | Deductive proof (SMT-based) | High (POPL 2026 active) | Slow (10–30 min) | **Excellent** (DafnyPro 86% benchmark) |
| Kani | Rust (safe + unsafe) | Bounded model checking | Medium–High (AWS, Rust stdlib use) | **Fast** (1–5 min for loops) | Medium (simple assertions only) |
| Prusti | Rust (safe only) | Deductive proof via Viper | Medium (research) | Slow (20+ min) | Medium (proof engineering heavy) |
| Creusot | Rust (safe only) | Deductive proof via Why3 | Medium (research) | Slow (20+ min) | Medium (proof engineering heavy) |
| Gobra | Go | Deductive proof via Viper | Medium–High (ETH, industrial) | Medium (5–15 min) | Low–Medium (limited LLM work) |
| OpenJML | Java | Deductive proof (SMT-based) | Medium (2025 updates) | Slow (10–30 min) | Low (legacy style) |
| KeY | Java | Deductive proof (sequent calculus) | Medium (2024 stable) | Slow (15–60 min) | Low (interactive, heavy annotation) |
| icontract | Python | Runtime contracts (design-by-contract) | High (active, 2.7.3 recent) | **Very fast** (<1 sec) | Medium (no proof, just runtime check) |
| CrossHair | Python | Symbolic execution + contracts | Medium (0.0.109 recent) | Medium (1–5 min per function) | Medium (good for finding bugs, not proofs) |
| deal | Python | Runtime contracts + static checks | Medium (active) | **Very fast** (<1 sec) | Medium (lightweight, no proofs) |
| Nagini | Python | Deductive proof via Viper | Low (research, less active) | Slow (10+ min) | Low–Medium |
| SPARK/Ada | Ada | Deductive proof + flow analysis | Medium–High (ISO 26262 industrial) | Medium (5–15 min) | Low (specialized domain) |
| Lean 4 | Lean/any (extraction) | Proof assistant (tactic-based) | High (FRO active 2025–2026) | Very slow (human-scale proofs) | **Excellent** (AI backbone for IMO proofs) |
| F* | F* (compiles to C, OCaml, …) | Deductive proof (SMT-based) | Medium (Microsoft/Everest legacy) | Slow (10–30 min) | Low–Medium |

## Per-tool assessment

### Verus (Rust)
**Strengths:**
- Proven on large systems (OS kernels, verified Rust libs); nearest to production.
- Linear ghost types fit separation-logic patterns (e.g., API handler state).
- LLM-driven proof synthesis mature: VeruSAGE (Dec 2025) >80% on system tasks; VeruSyn fine-tuned 6.9M programs.
- Concurrency via explicit proof (atomic blocks, locks); suitable for refinement from serializable model.

**Weaknesses:**
- Slow CI loop (5–20 min per module); unsuitable for tight agent feedback.
- Steep learning curve (ghost state, separation logic); requires specialist annotation.
- Partial unsafe support (verified boundaries, not full unsafe verification).

### Dafny
**Strengths:**
- Verification-aware language; no manual ghost-type boilerplate.
- Cross-language compilation (C#, Java, Go, Rust, Python); fits multi-target stack.
- LLM proof generation state-of-art: DafnyPro (2026) 86% on DafnyBench (Claude 3.5 Sonnet); AxDafny iterative refinement.
- Active research (POPL 2026 workshop, verified AWS authorization engine).

**Weaknesses:**
- Moderate CI speed (10–30 min); not as fast as model checking.
- Language switching overhead (not native to handler language).
- Requires translating web API schemas into Dafny specs.

### Kani (Rust)
**Strengths:**
- Fully automated; minimal annotation; handles unsafe code (crucial for real Rust).
- Fast for small bounds (1–5 min), suitable for CI.
- Effective for loop invariants, overflow, and panics; ideal for safety properties.
- AWS-backed; growing adoption in stdlib verification.

**Weaknesses:**
- Bounded model checking: finite-loop unrolling limits scalability (e.g., unbounded web request streams).
- Cannot prove functional correctness (only safety properties).
- Monomorphic code only (no generics).

### Gobra (Go)
**Strengths:**
- Modular verifier targeting Go concurrency (goroutines, channels); fits handler concurrency patterns.
- Proves data-race freedom, memory safety, user specs; strong for concurrent API handlers.
- Industrial use (VerifiedSCION, cyber-trust routers, 2025 CCS publication).
- Moderate CI speed (5–15 min).

**Weaknesses:**
- Limited LLM work (no VeruSAGE-like ecosystem yet).
- Less mature than Verus in system code; smaller community.
- Channel verification requires explicit invariant specs (manual burden).

### Java (OpenJML, KeY)
**Strengths:**
- OpenJML actively maintained 2025–2026; supports Java 21.
- Large ecosystem of JML specs; legacy codebase support.

**Weaknesses:**
- Both tools slow (15–60 min); heavyweight proof loop.
- Low LLM friendliness (verbose JML syntax, legacy style).
- KeY requires interactive guidance; not batch-friendly for agent loops.

### Python (icontract, CrossHair, deal)
**Strengths:**
- icontract: runtime enforcement, zero annotation overhead (decorators), very fast (<1 sec).
- deal: lightweight static+dynamic checks.
- CrossHair: symbolic execution finds bugs automatically; good for quick feedback.

**Weaknesses:**
- No formal proof; only runtime contracts or bounded execution.
- Insufficient for provable invariant enforcement (agent cannot safely optimize).
- icontract/deal miss failures that don't hit the check; not sound.

### SPARK/Ada
**Strengths:**
- Deductive proof + flow analysis; strong for safety-critical (ISO 26262 multicore ECUs).
- Recent active work (NVIDIA compliance 2025, Exceptional_Cases aspect).
- Borrowing/ownership inspired by Rust; modern memory model.

**Weaknesses:**
- Domain-specific (avionics, automotive); not mainstream for web APIs.
- Limited ecosystem; specialized tooling and training overhead.

### Lean 4 & F*
**Strengths:**
- Lean 4: proof assistant of choice for AI-driven mathematics (AlphaProof, DeepSeek-Prover 2024–2025); Lean Atlas (human-AI collaboration).
- F*: verified compiler/protocol projects; strong SMT integration.

**Weaknesses:**
- Designed for mathematical proofs, not operational code verification.
- Very slow iteration (human-scale proof engineering).
- Language gap: extracting verified code to web API handlers is multi-step.
- Not intended for autonomous agent optimization loops.

## Fit for the workflow

**Best fit: Dafny + Verus (two-tier approach)**

1. **Dafny (front-end):** Developer writes invariants in natural language → LLM translates to Dafny specs (high success rate via AxDafny/DafnyPro) → verification in CI (10–30 min).
2. **Verus (for Rust handlers, optional second tier):** If Dafny proof fails or performance proof needed, rewrite handler in Verus for system-level guarantees. LLM-driven synthesis (VeruSAGE) mitigates annotation burden.

**Alternative (Go + Gobra):** If handler concurrency is a primary design concern, use Gobra directly on Go; strong channel/goroutine support; moderate LLM gap (smaller than Java).

**Not recommended for tight loops:**
- Java (slow, low LLM support).
- Python (no proof, runtime only).
- Lean/F* (not for operational code).

## Prototype ideas (1–2 days each)

1. **Dafny + DafnyPro on mock API spec:** Translate sample invariant (e.g., "request_id is unique") to Dafny, measure LLM success rate on proof.
2. **Kani on single handler:** Bounded verification of a GET handler for overflow, panic, assertion safety; measure CI latency.
3. **Gobra on simple Go handler with goroutines:** Verify data-race freedom in concurrent request processing; measure annotation effort vs. Verus.
4. **Hybrid Python (icontract + CrossHair):** Fast runtime contracts for development + symbolic bug-finding; measure missed-check rate vs. formal proof.

## Sources

- [Verus: Proof-Carrying Rust (OSDI 2024)](https://www.emergentmind.com/topics/verus)
- [VeruSAGE: Agent-Based Verification (arXiv 2512.18436, Dec 2025)](https://arxiv.org/abs/2512.18436)
- [VeruSyn & fine-tuned LLMs (Feb 2026)](https://arxiv.org/abs/2512.18436)
- [Dafny 2026 Workshop (POPL 2026)](https://popl26.sigplan.org/home/dafny-2026)
- [DafnyPro: LLM-Assisted Verification (86% success)](https://popl26.sigplan.org/details/dafny-2026-papers/12/DafnyPro-LLM-Assisted-Automated-Verification-for-Dafny-Programs)
- [AxDafny: Agentic Verified Code (arXiv 2606.32007)](https://arxiv.org/html/2606.32007)
- [Kani Model Checker (arXiv 2607.01504, 2025)](https://arxiv.org/html/2607.01504v1)
- [Rust stdlib verification survey (Rust Project Goals)](https://rust-lang.github.io/rust-project-goals/2024h2/std-verification.html)
- [Gobra: Modular Go Verification (ETH Zurich)](https://www.pm.inf.ethz.ch/research/gobra.html)
- [OpenJML GitHub](https://github.com/openjml)
- [CrossHair docs](https://crosshair.readthedocs.io)
- [icontract PyPI](https://pypi.org/project/icontract/)
- [deal ReadTheDocs](https://deal.readthedocs.io)
- [SPARK Ada: Concurrent Systems (AdaCore, ISO 26262 2025)](https://www.adacore.com/videos/introduction-to-formal-verification-with-spark)
- [Lean FRO Roadmap Y3 (Aug 2025–Jul 2026)](https://lean-lang.org/fro/roadmap/y3/)
- [Lean Atlas: Human-AI Proof Collaboration (arXiv 2604.16347)](https://arxiv.org/html/2604.16347v1)

## Open questions

1. **Agent proof-synthesis wall:** VeruSAGE >80% on system tasks, but success rate on web-API-specific patterns (concurrency, state transitions, migrations) unknown. Prototype needed.
2. **LLM translation quality (invariants → specs):** No benchmark for natural-language-to-Dafny translation fidelity; DafnyPro assumes spec is given.
3. **Concurrency semantics:** Verus/Dafny proof of concurrent handlers not yet studied in LLM-agent context; migration-while-serving scenario unclear.
4. **CI cost-benefit:** Is 10–30 min Dafny proof acceptable for agent optimization loop, or must fast model checking (Kani, CrossHair) be primary? Depends on optimization frequency.
5. **Hybrid dispatch:** Should agent try lightweight check (icontract/Kani) first, escalate to Dafny/Verus on failure? Decision tree not yet explored.
