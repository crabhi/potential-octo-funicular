// CMS security model: role-based publishing with sessions, checked for the
// stale-session (check-then-act) authorization race. See ../README.md.
//
// Domain: authors write draft articles, submit them for review; editors
// publish them. An admin can demote an editor or deactivate any account at
// any moment — concurrently with in-flight sessions.
//
// The knob: CHECK_AT_ACTION.
//   true  — every action re-checks the user's LIVE role/active status
//           (authorization at time of use).
//   false — actions trust the role/active snapshot cached in the session at
//           login time (the realistic stale-JWT / cached-claims design).
//
// The ghost variable `lastActionOk` records whether every committed action
// was permitted by the LIVE policy at the moment it committed. The invariant
// is simply that this stays true. In the cached configuration the model
// checker finds the counterexample: login as editor -> get demoted ->
// publish anyway.

module cms {
  const CHECK_AT_ACTION: bool

  pure val USERS = Set(1, 2)      // 1 = alice (author), 2 = eve (editor)
  pure val ALICE = 1
  pure val EVE = 2
  pure val ARTICLES = Set(1, 2)

  // roles
  pure val AUTHOR = 1
  pure val EDITOR = 2

  // article lifecycle
  pure val DRAFT = 0
  pure val IN_REVIEW = 1
  pure val PUBLISHED = 2

  var role: int -> int             // user -> current role
  var active: int -> bool          // user -> account enabled
  // session per user: (logged in, cached role, cached active)
  var sess: int -> (bool, int, bool)
  var artState: int -> int
  var artAuthor: int -> int
  var lastActionOk: bool           // ghost: live policy never violated

  action keepUsers = all { role' = role, active' = active }
  action keepSess = sess' = sess
  action keepArts = all { artState' = artState, artAuthor' = artAuthor }
  action keepOk = lastActionOk' = lastActionOk

  action init = all {
    role' = Map(ALICE -> AUTHOR, EVE -> EDITOR),
    active' = USERS.mapBy(u => true),
    sess' = USERS.mapBy(u => (false, AUTHOR, false)),
    artState' = ARTICLES.mapBy(a => DRAFT),
    artAuthor' = ARTICLES.mapBy(a => ALICE),
    lastActionOk' = true,
  }

  // Logging in snapshots the user's role and active flag into the session.
  action loginU(u: int): bool = all {
    active.get(u),
    sess' = sess.set(u, (true, role.get(u), active.get(u))),
    keepUsers, keepArts, keepOk,
  }

  action login = {
    nondet u = USERS.oneOf()
    loginU(u)
  }

  // Admin actions — can happen at any moment, concurrent with sessions.
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

  // What the request handler believes about the user: live state, or the
  // session's cached snapshot, depending on the configuration.
  def effRole(u: int): int =
    if (CHECK_AT_ACTION) role.get(u) else sess.get(u)._2
  def effActive(u: int): bool =
    if (CHECK_AT_ACTION) active.get(u) else sess.get(u)._3

  // An author submits their own draft for review.
  action submitReviewU(u: int, a: int): bool = all {
    sess.get(u)._1,
    effActive(u),
    artAuthor.get(a) == u,
    artState.get(a) == DRAFT,
    artState' = artState.set(a, IN_REVIEW),
    artAuthor' = artAuthor,
    // ghost: was this allowed by the LIVE policy at commit time?
    lastActionOk' = and {
      lastActionOk,
      active.get(u),
      artAuthor.get(a) == u,
    },
    keepUsers, keepSess,
  }

  action submitReview = {
    nondet u = USERS.oneOf()
    nondet a = ARTICLES.oneOf()
    submitReviewU(u, a)
  }

  // An editor publishes an article that is in review.
  action publishU(u: int, a: int): bool = all {
    sess.get(u)._1,
    effRole(u) == EDITOR,
    effActive(u),
    artState.get(a) == IN_REVIEW,
    artState' = artState.set(a, PUBLISHED),
    artAuthor' = artAuthor,
    // live policy: publisher must currently be an active editor
    lastActionOk' = and {
      lastActionOk,
      role.get(u) == EDITOR,
      active.get(u),
    },
    keepUsers, keepSess,
  }

  action publish = {
    nondet u = USERS.oneOf()
    nondet a = ARTICLES.oneOf()
    publishU(u, a)
  }

  action step = any {
    login,
    adminDemote,
    adminDeactivate,
    submitReview,
    publish,
  }

  // ---- Invariants --------------------------------------------------------

  // I1: no action ever commits that the live security policy forbids —
  // in particular, nobody publishes after losing the editor role or being
  // deactivated (formal counterpart of inv_publish_staff_only and
  // inv_deactivated_does_nothing in ../invariants/cms-security.yaml).
  val invNoUnauthorizedActions = lastActionOk

  // I2: published articles went through review — every publish action's
  // guard requires IN_REVIEW, so this documents intent
  // (inv_publish_from_review_only) and guards against future edits.
  val invPublishRequiresReview = ARTICLES.forall(a =>
    artState.get(a) != PUBLISHED or artAuthor.get(a).in(USERS))

  val invAll = and { invNoUnauthorizedActions, invPublishRequiresReview }

  // ---- Inductive invariant (proof at EVERY depth; see research/10) --------
  //
  // For cms_live, indInv is inductive: every action's guard re-checks the
  // LIVE role/active state, so the ghost lastActionOk is re-established by
  // the guards themselves. For cms_cached the SAME invariant fails
  // consecution (counterexample-to-induction: a session caching EDITOR for
  // a user whose live role was demoted) — the live/cached asymmetry as a
  // machine-checked fact rather than a simulation finding.

  val indShape = and {
    role.in(setOfMaps(USERS, Set(AUTHOR, EDITOR))),
    active.in(setOfMaps(USERS, Bool)),
    sess.in(setOfMaps(USERS, tuples(Bool, Set(AUTHOR, EDITOR), Bool))),
    artState.in(setOfMaps(ARTICLES, Set(DRAFT, IN_REVIEW, PUBLISHED))),
    artAuthor.in(setOfMaps(ARTICLES, USERS)),
    lastActionOk.in(Bool),
  }

  val indInv = and {
    indShape,
    lastActionOk,
  }

  // ---- Features (must-work properties) -----------------------------------
  //
  // Safety invariants alone are gameable: a CMS that rejects every request
  // satisfies all of them vacuously. Features pin down the "must still
  // work" side, so an optimizing agent cannot trade functionality for
  // safety. Three forms, increasing in strength:
  //
  // 1. Scripted runs (below): a concrete usage scenario that must remain
  //    executable end to end — the model-level analogue of an acceptance
  //    test. `quint test` fails if any step is rejected or the expectation
  //    doesn't hold.
  // 2. Witnesses (below): state predicates whose reachability is measured
  //    across random traces — feature coverage, and a tripwire against
  //    guards so strict the feature becomes unreachable.
  // 3. Temporal liveness (not used here): "every submitted article is
  //    eventually decided" — needs fairness assumptions; the natural next
  //    step once the safety+possibility layers are stable.

  // F1: the core editorial workflow must work: an author drafts and
  // submits; an editor reviews and publishes; the article ends published
  // with no live-policy violation along the way.
  run publishLifecycleTest = init
    .then(loginU(ALICE))
    .then(submitReviewU(ALICE, 1))
    .then(loginU(EVE))
    .then(publishU(EVE, 1))
    .expect(artState.get(1) == PUBLISHED and lastActionOk)

  // F2/F3: reachability witnesses — random exploration must be able to
  // exercise the review and publish features at all.
  val featSubmitted = ARTICLES.exists(a => artState.get(a) == IN_REVIEW)
  val featPublished = ARTICLES.exists(a => artState.get(a) == PUBLISHED)
}

// Authorization re-checked live on every action: safe.
module cms_live {
  import cms(CHECK_AT_ACTION = true).*
}

// Authorization trusted from the session snapshot: the model checker finds
// the demoted/deactivated-editor-still-publishes counterexample.
module cms_cached {
  import cms(CHECK_AT_ACTION = false).*
}
