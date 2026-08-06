# CLAUDE.md

## Goal

Research **formal rules as a higher level of abstraction for programming**:
the developer states invariants; LLMs translate and generate code; reasoning
engines (SMT, model checkers, provers) — not humans — hold the code to the
rules. Prefer proving that something *never/always* happens; tests are only
an approximation for the model↔code boundary.

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

## Environment notes

- GitHub downloads are proxy-blocked: TLC via `nightly.tlapl.us`, Dafny via
  `dotnet tool install`, Verus unavailable; mypyvy via git clone.
- Quint: use `--backend typescript` (Rust evaluator download blocked).
  Apalache inductive mode needs shape constraints for every variable
  (`x.in(S)`, `setOfMaps(...)`); no infinite domains in map codomains —
  encode counters as finite flags.
- Postgres 16 local (`service postgresql start`); headless repairer:
  `claude -p --permission-mode acceptEdits --allowedTools Read,Edit`.
