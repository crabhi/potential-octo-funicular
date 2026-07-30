# Suggested (non-blocking) model addition: parameterized admin actions

**Status: not a blocker.** This prototype (Track B, trace validation) works
end to end without this change — see `README.md` for the captured PASS/FAIL
runs. This note records a caveat discovered while building it, for whoever
picks up the model next.

## What's missing

`../model/cms.qnt` only exposes the admin actions as bare nondet actions:

```qnt
action adminDemote = {
  nondet u = USERS.oneOf()
  all { role.get(u) == EDITOR, ... }
}

action adminDeactivate = {
  nondet u = USERS.oneOf()
  all { active.get(u), ... }
}
```

There is no parameterized `adminDemoteU(u: int): bool` / `adminDeactivateU(u:
int): bool` counterpart, unlike `loginU(u)` / `submitReviewU(u, a)` /
`publishU(u, a)`, which all have both a parameterized form and a nondet
wrapper (`login`, `submitReview`, `publish`) that picks randomly among
users/articles.

## Why it's a problem in general (but not here)

`log2run.py` compiles a logged `adminDemote`/`adminDeactivate` event into a
bare `.then(adminDemote)` / `.then(adminDeactivate)` — it cannot say *which*
user the model should apply the action to. This happens to work
deterministically for every trace this prototype's `driver.py` can produce,
because the driver's fixed 2-user universe (alice=author, eve=editor) makes
the nondet choice unique by construction: `adminDemote`'s guard
`role.get(u) == EDITOR` is only satisfiable by eve (alice is never an
editor in these scenarios), so `.then(adminDemote)` behaves as if it were
`.then(adminDemoteU(EVE))`. Verified empirically: 10000-sample and repeated
`quint test` runs of the compiled traces are 100% consistent (see
`README.md`).

It would **not** work if a future scenario had two simultaneously-eligible
targets (e.g. two active editors, and the log says "demote user X" but the
model could nondet-pick either editor) — the compiled run would be
ambiguous, and `quint test` could pass or fail depending on the random
seed. `log2run.py`'s docstring flags this caveat explicitly.

## The suggested addition (mirrors the loginU/login pattern)

```qnt
action adminDemoteU(u: int): bool = all {
  role.get(u) == EDITOR,
  role' = role.set(u, AUTHOR),
  active' = active,
  keepSess, keepArts, keepOk,
}

action adminDemote = {
  nondet u = USERS.oneOf()
  adminDemoteU(u)
}

action adminDeactivateU(u: int): bool = all {
  active.get(u),
  active' = active.set(u, false),
  role' = role,
  keepSess, keepArts, keepOk,
}

action adminDeactivate = {
  nondet u = USERS.oneOf()
  adminDeactivateU(u)
}
```

With this in place, `log2run.py` could emit `.then(adminDemoteU(2))` /
`.then(adminDeactivateU(2))` directly from the logged `{"user": <id>}` and
the ambiguity above disappears unconditionally, not just by construction of
the driver's restricted universe.

## Recommendation

Low priority. Track B's hypothesis (client-side logs suffice to catch the
cached-auth conformance violation) is already validated without this
change. Make the change only if a future scenario needs to target a
specific admin action among multiple simultaneously-eligible users.
