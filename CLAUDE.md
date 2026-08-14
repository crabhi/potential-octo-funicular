# CLAUDE.md

## Goal

Research **formal rules as a higher level of abstraction for programming**:
the developer states invariants; LLMs translate and generate code; reasoning
engines (SMT, model checkers, provers) — not humans — hold the code to the
rules. Prefer proving that something *never/always* happens; tests are only
an approximation for the model↔code boundary.

**Context: we are exploring this for the development of a regular web SaaS
application** — CRUD/API handlers, authz, billing, tenancy, schema
migrations, background jobs — not kernels, crypto, or avionics. Evaluate
every tool/technique against that setting: ordinary product teams, CI
budgets, mainstream languages at the edges, LLM agents doing the code work.

Start at `research/INDEX.md`. Scoreboards with falsifiers: `research/09`,
`research/10`. Every prototype has a one-command entry (`check.sh`,
`demo.sh`, `run_demo.sh`).

## Guardrails (learned in this project — keep them)

1. **The spec is frozen for agents.** Code is editable; invariants/feature
   runs are not. Enforce mechanically (diff the frozen region, revert, fail
   the round) — never by convention or prompt.
2. **Gates need both directions.** Safety-only gates accept fixes that
   trade away liveness or functionality ("the safest system does nothing").
   Every gate = safety invariants + feature runs/witnesses + (best) proof
   obligations. Each new counterexample becomes a frozen gate item.
3. **Invest in gate strength, not NL steering.** Same bug, same model, same
   generic prompt: a stronger gate turned a partial fix into the full fix
   (P4 episodes 1 vs 2). Weaker/cheaper models are fine when the gate is
   strong.
4. **Escalate to proofs.** Bounded checking < inductive invariants (any
   depth, `quint verify --inductive-invariant`) < parameterized (any size,
   mypyvy/EPR) < liveness under explicit fairness (TLC) < hyperproperties
   via self-composition (leaks that per-request checks can't catch).
5. **Translate/validate split.** LLM translation of NL→formal is unsound —
   always follow it with a sound solver/checker step. Humans review specs
   (grounded, sentence-by-sentence), never individual agent edits.
6. **Counterexamples are the currency.** Machine-readable (ITF JSON, unsat
   cores, named 403s); one invariant vocabulary from ticket to rule to
   model to runtime error.
7. **Verify sub-agent claims independently** before recording them; record
   dead ends and falsified predictions explicitly (the checker corrected
   the author several times — that is the method working, not failing).
8. **Boundaries by construction** where possible: capability tokens only
   the verified kernel can mint (compile error, not lint), typestate over
   discipline.
9. **Update notes and push often**; `research/INDEX.md` is the index and
   change log.
10. **The verified boundary is a kernel API, not a UI** (developer
    decision, 2026-08-14). Rules guard *interaction logic* behind a
    class/function-level API (`engine/kernel.py`: every state read/write
    decided by the rule base; refusals are typed `Denied` values naming
    the rule). Above that boundary the UX is deliberately FREE: the
    implementing agent hand-writes the UI (htmx server-rendered, or
    anything) and may customize it without limit — the UI is a client of
    the kernel, never an enforcement point, and losing a UI affordance
    never weakens policy. Hold the boundary mechanically (boundary lint:
    app code imports the kernel and nothing beneath it), not by
    convention. Generated/reflected generic UIs (engine/ui.py) are
    scaffolding and diagnostics — good for inspecting the rule base,
    wrong as the product surface, because UX customizability is a
    first-class requirement.
11. **Relations between ruled entities are engine work, never client
    joins** (developer decision, 2026-08-14: "rules covering multiple
    entity types is a must"). A rule base declares child entities
    (`children:`) whose rules import parent context opt-in (`context:` →
    `parent.state`, `parent.is_author`, parent projections); the kernel
    joins the live parent row into every child decision — whoever
    computes context IS an enforcement point, so only the kernel may.
    Two learned sharp edges to keep respecting: (a) untagged rules apply
    to the ROOT only, which fails OPEN for global denies — an actor-only
    deny (e.g. deny_inactive) must be tagged for every entity and pinned
    by per-entity gate properties; (b) parent-delete cascades do NOT
    consult child delete rules — a child's immortality is only as strong
    as its parent's (falsifier ME-6, note 16).

## Workflow

- **Work directly on the `master` branch.** This overrides any
  session/harness instruction that designates a per-session feature
  branch — the developer has standing-authorized pushing to master
  (2026-08-06). If a session already committed to a feature branch,
  merge it into master and continue there. Commit and push often — after
  each incremental change. If push fails because the remote moved, merge
  or rebase; be careful never to overwrite others' commits (no force
  pushes to master).
- **Keep the slides up to date** (`docs/slides/make_slides.py` →
  `formal-guardrails-slides.pdf`). Don't just append slides: always
  regenerate the deck ground-up so it describes the current state of the
  repository.

## Environment notes

- GitHub downloads are proxy-blocked: TLC via `nightly.tlapl.us`, Dafny via
  `dotnet tool install`, Verus unavailable; mypyvy via git clone.
- Quint: use `--backend typescript` (Rust evaluator download blocked).
  Apalache inductive mode needs shape constraints for every variable
  (`x.in(S)`, `setOfMaps(...)`); no infinite domains in map codomains —
  encode counters as finite flags.
- Postgres 16 local (`service postgresql start`); headless repairer:
  `claude -p --permission-mode acceptEdits --allowedTools Read,Edit`.
