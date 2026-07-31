# Track K — noninterference: a hyperproperty the invariants couldn't say

**The claim being proven:** "draft article contents never influence what an
anonymous user observes."

**Why this needed a new concept.** Every property in this project so far
constrains single executions ("no request ever reads a dropped column").
The claim above is different in kind: it relates **pairs** of executions.
Run the CMS twice — same public actions, but the authors type *different
draft text* in the two runs. If any anonymous-visible output differs
between the runs, the difference can only have come from the secret drafts:
an information leak. Noninterference is therefore a **2-safety
hyperproperty**; no single-trace invariant can express it, and per-request
authorization checks cannot enforce it (each individual request can be
perfectly authorized while the *aggregate* behavior still leaks — see the
negative control below).

**Technique: self-composition** (`cms_ni.qnt`). One Quint module holds two
copies of the content state (`cL`, `cR`) driven by synchronized public
actions; draft edits take *independent* nondeterministic values in the two
worlds (the secret input). The observation function is what anonymous
requests can see: GET results (state; body only when published, uniform 404
otherwise) and search-by-content match counts. The hyperproperty becomes an
ordinary invariant of the composed system: `obsEqual`.

**Declassification choice.** In a real CMS the draft text becomes the
published text, so publication legitimately reveals it. We model publish as
the declassification point: the published value is a public input, equal in
both worlds from that moment. The theorem then reads: *nothing about
draft-time contents — which diverge arbitrarily through any number of
edits — is anonymous-observable, ever, except the finally published value.*

## Results

- **Safe configuration** (search indexes published articles only):
  noninterference **proven at every depth** — `indInv` (shape + "published
  contents agree") passes Apalache's inductive-invariant check: base,
  consecution, and `indInv ⇒ obsEqual`, in ~6s. Not sampling, not bounded:
  a proof for all executions of any length (at these constants).
- **Leaky configuration** (`SEARCH_INDEXES_DRAFTS = true` — the search/count
  endpoint also matches drafts, a classic production leak): counterexample
  in under a second. The distinguisher found by the checker: both worlds
  hold only DRAFTS (nothing published, nothing ever revealed), yet after a
  draft edit that wrote value 1 in world L and value 2 in world R, the
  anonymous search count for value 1 is 2 in L but 1 in R. An anonymous
  user, issuing only authorized requests, learns draft content.

```
$ quint verify cms_ni.qnt --main cms_ni_safe  --inductive-invariant indInv --invariant obsEqual
[ok] No violation found (6112ms)
$ quint run   cms_ni.qnt --main cms_ni_leaky --invariant obsEqual
[violation] ... cL: Map(1 -> 1, ...) vs cR: Map(1 -> 2, ...)   # searchCount(1) differs
```

## Why this matters for the project

- The per-request authorization rules (P2 layer, kernel proofs, Grant
  tokens) are all satisfied in the leaky configuration — **every request is
  authorized, and the system still leaks**. This class of requirement
  ("anonymous users cannot learn draft content", "tenant A cannot learn
  about tenant B") is common in real security tickets and was previously
  outside our formal language entirely.
- The pattern is reusable: secret = any non-public field; observation
  function = the anonymous/foreign-tenant API surface; declassification =
  the legitimate release points. Self-composition turns it into an
  ordinary invariant our whole existing pipeline (oracle, model checking,
  inductive proof, repair gates) can process.

## Honest limits

- Model-level proof: fidelity to the Rust app is untested (the app's search
  endpoint doesn't exist yet; if one is added, MBT/trace-validation should
  target this model). Timing/size side channels are out of scope.
- Fixed constants (2 articles, 2 values); parameterized generalization
  would follow Track J's approach.
- Declassify-at-publish means the model does not track "the draft I edited
  is the text that got published" — that flow is deliberately outside the
  secrecy claim.

Verdict for the Track K scoreboard row: **WORKED** — proof at inductive
level for the safe design, machine-found two-world distinguisher for the
leaky one.
