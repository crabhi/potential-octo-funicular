# P2 — invariant oracle

A small Python CLI that takes developer invariants written in a restricted
typed schema and uses **Z3** to answer: *are these invariants contradictory,
redundant, vacuous, or surprising?* — before any code exists.

## Where this sits in the pipeline

From `research/00-project-brief.md`, the intended workflow is:

```
1. Developer states invariants in NL.
2. LLM translates them into a formal language; developer reviews.
3. A reasoning engine can be queried for contradictions or unexpected
   outcomes of the invariant set (before any code exists).   <-- this prototype
4. Formal requirements verify actual system behavior.
5. Agent optimizes code within the formal constraints.
```

`research/07-synthesis.md` (decision D2) proposes exactly this: assert all
invariants in Z3, use the **unsat core** to name contradictions, enumerate
**witness models** to catch unexpected-but-allowed states, add a
**vacuity** pass to catch dead/tautological/redundant invariants, and
report a rich verdict taxonomy (`VALID / INVALID / SATISFIABLE /
IMPOSSIBLE`, modeled on AWS Bedrock Automated Reasoning) rather than a bare
pass/fail. This prototype is that CLI, with no dependency on P1's spec
language choice.

The typed schema here (bools/ints-with-range/enums, comparisons,
and/or/not/implies, arithmetic) is deliberately the "restricted typed rule
schema" style from D1/D2, not a general-purpose spec language — it is meant
to be reviewable sentence-by-sentence by a developer and reliably
translatable by an LLM, unlike full TLA+/Quint.

## Setup

```bash
cd prototypes/p2-invariant-oracle
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.11 (developed/tested against it). `z3-solver` and
`pyyaml` are the only runtime dependencies; `pytest` is only needed to run
the test suite (`pip install pytest`).

## Invariant file format

```yaml
variables:
  phase:
    type: enum
    values: [expand, backfill, contract, done]
  version_skew:
    type: int
    min: 0
    max: 3
  old_running:
    type: bool

invariants:
  - name: inv_skew_bound
    description: "At most one version of app code may run concurrently."
    formula: "version_skew <= 1"
  - name: inv_contract_needs_no_old
    description: "Contract may not begin while an old instance is running."
    formula: "implies(phase == \"contract\", not old_running)"
```

- **Variables**: `bool`, `int` (optional `min`/`max`, becomes an unconditional
  domain constraint), or `enum` (`values:` list; each variable gets its own
  Z3 `EnumSort`).
- **Invariants**: `name` (used in unsat cores and vacuity reports),
  `description` (the original natural-language sentence, so machine output
  can be traced back to what the developer said), `formula`.
- **Formula language** (`oracle/expr.py`): a whitelisted subset of Python
  expression syntax, parsed with `ast` and compiled to Z3 terms —
  `and` / `or` / `not`, comparisons (`==, !=, <, <=, >, >=`, including
  chained comparisons like `0 <= x <= 3`), arithmetic (`+ - * /`),
  `implies(a, b)` (the one allowed function call), and enum string literals
  compared directly against an enum variable (`phase == "expand"`). Every
  other AST node (attribute access, subscripting, other calls, lambdas,
  comprehensions, ...) is rejected — the parser is a closed whitelist, not a
  blocklist, so it is safe to feed it LLM-generated formulas.

## CLI

```
python -m oracle check FILE [--json]
python -m oracle witness FILE [-n K] [--json]
python -m oracle vacuity FILE [--json]
python -m oracle claim FILE --claim EXPR [--json]
```

`--json` on every subcommand for machine consumption (feeding results back
to an LLM agent).

### `check` — contradiction detection via unsat core

Asserts every invariant with `assert_and_track`; on UNSAT, maps the core
straight back to invariant names.

```
$ python -m oracle check examples/consistent.yaml
Verdict: CONSISTENT

Witness model:
phase   column_state  version_skew  old_running  new_running  reads_absent_column
------  ------------  ------------  -----------  -----------  -------------------
expand  write_only    0             False        False        False

$ python -m oracle check examples/contradictory.yaml
Verdict: IMPOSSIBLE

Unsat core (minimal conflicting invariants):
  - inv_skew_bound: At most one version of app code (old vs. new) may run concurrently during any migration phase.
  - inv_skew_at_least_two: During a rolling deploy at least two app versions must be able to run concurrently so there is never a request-serving gap.
```

`contradictory.yaml` is `consistent.yaml` plus one invariant a second
developer added independently (`version_skew >= 2`, for "zero-downtime
rolling deploy"); the core names exactly the two invariants that conflict,
none of the unrelated ones.

### `witness` — enumerate diverse satisfying models

Blocks each exact prior assignment and re-solves, so a developer can eyeball
"did I expect this to be allowed?"

```
$ python -m oracle witness examples/surprising.yaml -n 40 --json | \
    python3 -c "import json,sys; d=json.load(sys.stdin); \
    print([w for w in d['witnesses'] if w['phase']=='contract' and w['old_running']])"
[{'phase': 'contract', 'column_state': 'delete_only', 'version_skew': 0,
  'old_running': True, 'new_running': False, 'reads_absent_column': False}]
```

`surprising.yaml` is `consistent.yaml` with the guard
`inv_contract_needs_no_old` removed (a developer forgot it, or assumed it
followed from something else). `check` still reports CONSISTENT — but
enumerating witnesses turns up a model with `phase = contract` and
`old_running = True`: the migration is dropping the column while an old
binary that may still touch it is up. That is exactly the "surprising but
allowed" state D2 is meant to surface before any code exists. (72 total
models satisfy `surprising.yaml`; this one shows up by `-n 40` — enumeration
order is whatever Z3 returns, not sorted by "interestingness", so a real
workflow would want either a larger `-n` or a targeted `claim` query, which
is what `claim` is for.)

### `vacuity` — redundancy / tautology check per invariant

For each invariant: `¬invariant` alone unsat ⇒ **TAUTOLOGY** (always true
regardless of the other invariants); `others ∧ ¬invariant` unsat ⇒
**REDUNDANT** (implied by the rest); otherwise **OK**.

```
$ python -m oracle vacuity examples/consistent.yaml
  inv_skew_bound             OK   ...
  inv_no_read_absent         OK   ...
  inv_expand_state           OK   ...
  inv_backfill_state         OK   ...
  inv_contract_state         OK   ...
  inv_contract_needs_no_old  OK   ...
  inv_done_state             OK   ...
```

If the base invariant set is itself UNSAT, `vacuity` reports top-level
`IMPOSSIBLE` and skips the per-invariant table (there's nothing meaningful
to say about redundancy in an inconsistent set — run `check` first).

### `claim` — verdict taxonomy (AWS Bedrock Automated Reasoning style)

```
$ python -m oracle claim examples/consistent.yaml \
    --claim 'implies(phase == "contract", not old_running)'
Verdict: VALID
invariants entail the claim ...

$ python -m oracle claim examples/surprising.yaml \
    --claim 'implies(phase == "contract", not old_running)'
Verdict: SATISFIABLE
both the claim and its negation are consistent with the invariants
witness_claim_true:  ... phase=expand ...
witness_claim_false: ... phase=contract, old_running=True ...

$ python -m oracle claim examples/contradictory.yaml \
    --claim 'implies(phase == "contract", not old_running)'
Verdict: IMPOSSIBLE
the invariant set itself is unsatisfiable
```

- **VALID**: invariants ⇒ claim (`invariants ∧ ¬claim` is UNSAT).
- **INVALID**: invariants ⇒ ¬claim (`invariants ∧ claim` is UNSAT) — e.g.
  `claim examples/consistent.yaml --claim "version_skew >= 2"` returns
  INVALID, since `inv_skew_bound` already forces `version_skew <= 1`.
- **SATISFIABLE**: both claim and ¬claim are consistent with the
  invariants — shown with one witness of each.
- **IMPOSSIBLE**: the invariants themselves are unsatisfiable (claim is
  moot).

(`TRANSLATION_AMBIGUOUS` from the Bedrock taxonomy doesn't apply here since
there's no NL→formal translation step inside this tool — that happens
upstream, by the LLM in pipeline step 2.)

## Examples

All in `examples/`, themed on the brief's domain (web API + online DB
migration, F1-style element lifecycle `Absent -> WriteOnly -> Present ->
DeleteOnly` plus a version-skew bound):

- `consistent.yaml` — phase/column-state invariants, a skew bound, and a
  guard that contract can't start while an old instance is running. SAT,
  vacuity all OK.
- `contradictory.yaml` — `consistent.yaml` plus a second, independently
  authored invariant (`version_skew >= 2`) that directly conflicts with the
  skew bound. `check` reports IMPOSSIBLE with a two-invariant unsat core.
- `surprising.yaml` — `consistent.yaml` minus the "no old instance during
  contract" guard. Still SAT; `witness` reveals the unguarded state.

## Tests

```bash
source .venv/bin/activate
pip install pytest
python -m pytest tests/ -v
```

15 tests, all passing at the time of writing: each subcommand against each
example (asserting the exact verdicts/unsat-core/witness contents described
above), a synthetic tautology+redundancy case for `vacuity`, a VALID/INVALID
case pair for `claim`, and one check that the expression parser rejects an
`__import__(...)` escape attempt (whitelist, not blocklist).

## Limitations

- **Enumeration order is not "interesting-first"**: `witness` blocks exact
  prior assignments and re-solves; Z3 tends to return "nearby" models
  first, so a genuinely surprising state can be buried deep in the
  enumeration for larger models (see the `surprising.yaml` example needing
  `-n 40` out of 72 total models). A smarter version would bias for
  diversity (e.g. maximize Hamming distance from prior witnesses, or ask
  for one witness per enum value of each variable) rather than plain
  blocking.
- **No quantifiers, no time**: this is a single-state, propositional/linear-
  arithmetic snapshot — it cannot express "eventually" or "for all requests
  in flight", which is exactly why the brief's D3 (temporal/concurrency
  model) is a separate prototype (P1, Quint/TLA+). This oracle is meant to
  sanity-check the *static* invariant set that later gets compiled into
  that model's invariant section.
- **Vacuity is per-invariant, not per-subformula**: it flags a whole
  invariant as redundant/tautological, not sub-clauses within one
  invariant (the D2 finding mentions subformula-level vacuity as an
  emerging technique; out of scope here for simplicity).
- **Unsat cores are "an" unsat core, not guaranteed minimal**: Z3's default
  core from `assert_and_track` is usually small in practice (as seen in the
  `contradictory.yaml` example, which returns exactly the two conflicting
  invariants) but is not guaranteed minimum-cardinality; a `check_min_core`
  pass (Z3 has one but it's not always necessary) could be added.
- **Claim/formula language has no float/real support and no
  quantifiers** — deliberately, to stay in a fast decidable fragment
  (linear integer arithmetic + enums + booleans) and to keep the parser
  small (~150 lines) and easy to audit for safety.

## Next steps

- Wire `claim` into an LLM agent loop: given a proposed code change, derive
  a claim about the new behavior and check it against the frozen
  invariants (ties into D5's "counterexample-feedback payload"), using
  `--json` output as the machine-readable interface.
- Cross-check against P1's Quint/TLA+ model once it exists: the typed
  invariants here are meant to compile into that model's invariant section
  (D1's two-layer spec) — worth a round-trip test that the same
  contradiction/witness stories show up in both layers.
- Bias `witness` enumeration toward diversity (e.g. one model per distinct
  enum-value combination touched by the invariants) instead of arbitrary
  Z3 model order, so `-n 5` reliably surfaces edge cases without needing
  `-n 40`.
- Add a `TRANSLATION_AMBIGUOUS`-equivalent: if this tool is ever handed the
  raw LLM output alongside the developer's original sentence, add a check
  that the compiled formula's vacuity/witness behavior doesn't silently
  drift from what the sentence plausibly meant.
