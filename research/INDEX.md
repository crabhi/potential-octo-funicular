# Research notes index

Keep this file current: one line per note, newest changes noted in the log.

| File | Topic | Status |
|------|-------|--------|
| [00-project-brief.md](00-project-brief.md) | Problem statement, system model, milestones | living |
| [01-spec-languages.md](01-spec-languages.md) | Specification languages & model checkers (TLA+, Quint, Alloy, P, ...) | draft |
| [02-runtime-verification.md](02-runtime-verification.md) | Runtime verification, trace checking, consistency checkers | draft |
| [03-code-level-verification.md](03-code-level-verification.md) | In-language verifiers (Verus, Dafny, KeY, Gobra, Nagini, ...) | draft |
| [04-reasoning-engines.md](04-reasoning-engines.md) | SMT solvers & querying invariants for contradictions | draft |
| [05-db-migrations-concurrency.md](05-db-migrations-concurrency.md) | Formalizing online schema migrations + concurrent requests | draft |
| [06-llm-formal-methods.md](06-llm-formal-methods.md) | LLM x formal methods: spec synthesis, verified codegen, agent loops | draft |
| [07-synthesis.md](07-synthesis.md) | Cross-cutting synthesis: candidate architectures & recommendation | draft |
| [08-workflow-vision.md](08-workflow-vision.md) | Holistic workflow: roles, contract, novelty, adoption path | draft |
| [09-bridging-the-gap.md](09-bridging-the-gap.md) | M4 phase log: five bridge tracks, scoreboard, episode results | living |
| [10-proof-escalation.md](10-proof-escalation.md) | Proof escalation: inductive/parameterized/liveness/hyperproperties, phase 3 charter | living |
| [11-fstar-llm-abstraction.md](11-fstar-llm-abstraction.md) | F* as rule language for LLM workflow? Verdict: not primary for SaaS; steal 3DGen DSL pattern | draft |
| [12-rung5-proofs-in-code-from-spec.md](12-rung5-proofs-in-code-from-spec.md) | Rung 5 expanded: five patterns for proofs-in-code / code-from-spec in an LLM-built SaaS; Cedar/Dafny/Verus evidence; gaps we can own | draft |
| [13-rule-based-cms.md](13-rule-based-cms.md) | Rule-based systems as the programming surface: rules ARE the program, solver reviews the rule base, engine proven once; falsifiers RB1–RB5 | draft |
| [14-developer-experience.md](14-developer-experience.md) | DX study: Flowdeck (multi-tenant kanban SaaS) built end to end as rules with a generic web UI; 4 rounds × 0.18 s, 2 real authz holes caught, frictions enumerated; falsifiers DX1–DX3 | draft |

Worked examples live under `examples/`: `examples/cms/` — a CMS guarded by
the full pipeline, formal-methods framing (spec beside code);
`examples/rule-driven-cms/` — the same domain rebuilt ground-up under the
rule-based framing (the rule base is the program; note 13); and
`examples/taskboard/` — Flowdeck, an end-to-end SaaS app with a clickable
UI derived from the rule base, plus the honest DEVLOG (note 14).

## Change log

- 2026-08-14 (developer experience, end to end): the developer asked to
  push on DX — build a full example application and report how development
  *feels*. Built `examples/taskboard/` (Flowdeck, multi-tenant team
  kanban): 7 tickets → 18 rules → frozen gate (13 ∀ / 8 ∃ / 2 gated
  entries / 5 features). Four analyzer rounds at ~0.18 s caught two real
  authorization holes (anonymous-assignee start via unguarded
  assignee_moves; admin_oversees granting staff the team's work), the
  order-naming of overlapping denies, and a provably dead containment
  rule; the real round-2 draft is preserved and gated forever. Generic
  engine growth: actor_fields, actor_matches_field projections (tenancy +
  assignment as booleans), has_-opt-out (vocabulary budget), and a
  **generic web UI** (engine/ui.py — board from lifecycle, buttons from
  the decision function, named-403 banners; the CMS gained a UI without a
  line changed). Screenshots in docs/slides/img/. Note 14 (falsifiers
  DX1–DX3); DEVLOG in the example; slides regenerated ground-up with the
  DX narrative and screenshots.

- 2026-08-11 (slides reworked): deck regenerated ground-up with a new
  structure — the rule-driven experiments lead, with real code on the
  slides (rules.yaml excerpts, gate files, analyzer PASS/FAIL output,
  the 403 body, the receivables demo transcript); act I compressed to a
  single evidence slide. Two concept slides added on request: what the
  gate is (frozen acceptance criteria, deliberately redundant with the
  rules, both directions) and why rules rather than free code under the
  gate (the act II vs act I comparison: proof vs sampling, no seam vs the
  conformance tax, bounded vs unbounded edit surface). 18 slides.

- 2026-08-11 (domain transfer tested): third service on the same rule
  engine — a receivables tracker (claims: amount + approximate payer name
  or exact reference + due date; bank transaction emails; overdue
  reminders). Transfer cost measured and three-way split: domain semantics
  = 290 lines YAML (money truth only from the bank feed, absolute tenant
  isolation, append-only ledger, calendar-guarded overdue — all
  ∀-checked); generic engine growth = ~100 net lines for ONE missing
  concept, time (declared date projections + engine clock + multi-source
  transitions + feature-clock steps); fuzzy/cross-item matching and
  reminder dedup stayed client-side per the projection boundary.
  Cross-episode finding: bot containment needed deny rules in the CMS but
  is provably-dead here (bots own nothing) — which regime applies is a
  solver query. New: RB2 concrete cost (26,880-situation exhaustive check,
  ~80s), RB6 (engine clock as trust root). Episode in note 13; slides
  regenerated. All 11 check.sh stages green.

- 2026-08-11 (import extension, RB1 tested): first post-v1 ticket for the
  rule-driven CMS — nightly import of published articles from mock
  publisher feeds. Background job = just another actor: the importer is an
  unprivileged HTTP client (role `importer`) under the same rules; imports
  land in review with mandatory provenance, containment rules cap a
  compromised pipeline at create/read/submit, editors still decide.
  Engine untouched (RB1 holds); gate language needed two generic
  extensions the episode forced: stale-authorship-assumption detection
  (silent-unsoundness class) and `lifecycle: only_into` (the naive
  `syndicate: draft→published` transition evades every rule-level
  property). Naive variant kept: 5 named findings vs the frozen gate;
  import_demo.py runs two "nights" end-to-end (7 imported, idempotent
  re-run, named 403s over HTTP). Episode recorded in note 13; slides
  regenerated.

- 2026-08-11 (rule-based reframing): the developer asked what ground-up
  development of a full web service looks like, and whether rule-based
  systems beat "formal methods" as the framing. Built
  `examples/rule-driven-cms/`: the whole CMS as one declarative rule base
  (105 lines) executed by a domain-free engine (~975 lines Python, zero
  domain words — proven by running a second service, tickets, on it
  unchanged). One condition grammar with two backends (runtime eval + Z3),
  agreement checked exhaustively over all 3,600 situations. Analyzer gates
  every rule change: dead rules, ∀-safety, ∃-possibility, lifecycle
  liveness, frozen feature runs with expected-denials-by-name. Buggy
  variant (privacy deny added, separation-of-duties deny removed) → 6
  named findings against the frozen gate; a redundant guard was *proven*
  dead and deleted during development. Verdict in
  13-rule-based-cms.md: rules as the programming surface, solver as
  reviewer, proofs concentrated on the once-proven engine (note 12
  pattern 1, widened from authz to the whole service); falsifiers RB1–RB5.
  Slides regenerated ground-up.

- 2026-08-06 (rung 5 expanded): 12-rung5-proofs-in-code-from-spec.md
  drafted from three parallel research sweeps. Rung 5 split into five
  patterns ranked for LLM-built SaaS: (1) verified engine + DSL surface —
  the 3DGen shape is now shipped thrice by AWS (Cedar with Lean proofs +
  proven-complete symbolic analysis, Bedrock AR checks, AgentCore Policy's
  NL→Cedar loop), confirming note 11's F3 direction; (2) proven kernel
  generated & embedded — track D validated at cloud scale (AWS IAM authz
  engine in Dafny→Java, 10⁹ req/s, spec closed by 10¹⁵-sample shadow
  testing); (3) proofs-in-code, Rust-only in practice (VeruSAGE 81% of 849
  real proof tasks at ~$5.61/task; Flux as cheap refinement tier);
  (4) by-construction types; (5) verified runtime enforcement. Key gaps
  found: NO published LLM-vericoded business logic anywhere (our lane);
  no verified schema-migration tool (we're the SOTA); no
  invariant→Postgres-constraint compiler. New falsifiers R1–R5 +
  prototypes P8 (Cedar shootout), P9 (invariant→constraint compiler).
  Slides regenerated (18 slides — new rung-5 patterns slide; roadmap
  updated).

- 2026-08-06 (workflow): new CLAUDE.md rules — work directly on master,
  commit+push per incremental change, and always regenerate the slide
  deck ground-up from the repo state. Applied: F* research merged to
  master; docs/slides regenerated from scratch (17 slides — now covers
  M4 phases 1–3, tracks A–M, P4/P5 results, the proof-escalation ladder,
  and the F* verdict; previously the deck stopped at M3).

- 2026-08-06: CLAUDE.md now states the evaluation context explicitly — a
  regular web SaaS application. 11-fstar-llm-abstraction.md drafted: F*
  desk research (Pulse/PulseCore, FStarDataSet ⅓–½ LLM proof rate vs
  Dafny 86%, 3DGen agent+DSL pattern, F* absent from POPL'26 vericoding
  benchmark). Verdict: not the primary rule language for SaaS; two ideas
  worth stealing (constrained-DSL-with-verified-toolchain, effects as
  by-construction boundaries). Falsifiers F1–F3 logged; hands-on parked
  on toolchain feasibility (GitHub 403; opam path untested). Also added
  the missing note-10 row to the table above.

- 2026-07-30 (M4 phase 2, "strong guarantees over NL guidance"): Track F —
  gate-strengthened repair loop forces the full fix in 1 round with an
  unchanged generic prompt (controlled comparison vs episode 1); Track G —
  authorization kernel boundary is now a compile error (Grant<Op> capability
  tokens), harness and proofs unchanged. See 09-bridging-the-gap.md.

- 2026-07-30 (M4 phase 1): five bridge tracks executed in parallel — A repair
  loop WORKED (1 round, exposed safety-only-gate liveness gap), B trace
  validation WORKED, C model-based testing WORKED (240/240 parity, 6/6
  divergences), D Dafny proven-kernel-to-Go WORKED, E Kani spike: exhaustive
  wins at finite domains, Kani at unbounded — see 09-bridging-the-gap.md.

- 2026-07-30: repo created; brief written; research agents dispatched for notes 01–06.
- 2026-07-30: 06-llm-formal-methods.md drafted.
- 2026-07-30: 05-db-migrations-concurrency.md drafted.
- 2026-07-30: all six research notes (01–06) drafted; 07-synthesis.md written with candidate architectures A/B/C, recommendation (hybrid C), and proposed prototypes P1–P4. Awaiting developer decision (M2).
- 2026-07-30: M2 decided — P1+P2+P3, Quint, Rust app, snapshot isolation (see 00-project-brief.md Decisions). Prototype work started under prototypes/.
- 2026-07-30: P1 done (prototypes/p1-migration-model/) — Quint model of expand/contract + concurrent requests under SI. The checker falsified two successive "correct" protocol versions (drain guard only at backfill; IS NULL backfill criterion) before the third passed simulation + Apalache. See P1 README.
- 2026-07-30: P2 done (prototypes/p2-invariant-oracle/) — Z3-backed CLI: check/witness/vacuity/claim with unsat cores and Bedrock-style verdicts; 15 tests green.
- 2026-07-30: ease-of-use pass — root README (repo entry point), P2 demo.sh, P1 prerequisites section; 08-workflow-vision.md added (holistic framing for slides/review).
- 2026-07-30: P3 done (prototypes/p3-conformance-harness/) — Rust axum API x2 versions + Postgres + trigger-based expand/contract migration under concurrent load; found & fixed a real TOCTOU race at contract cutover; negative test reproduces the no-drain anomaly (59 errors/run). M3 complete.
