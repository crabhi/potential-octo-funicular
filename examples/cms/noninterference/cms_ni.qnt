// Track K: noninterference for the CMS as a HYPERPROPERTY, via
// self-composition. See README.md.
//
// The property "anonymous users never learn draft content" is not a
// property of any single execution — it relates PAIRS of executions
// (a 2-safety hyperproperty). Technique: run two copies of the system,
// L and R, that receive identical PUBLIC inputs but may receive different
// SECRET inputs (draft contents). If every anonymous observation is equal
// in both worlds, draft content cannot influence what anonymous sees.
//
// Declassification design: in a real CMS the draft text literally becomes
// the published text, so publication legitimately reveals it. We model
// publish as the declassification point: the published text is a public
// input chosen at publish time (both worlds receive the same value). The
// theorem is then: NOTHING about draft-time contents — which diverge
// arbitrarily between the worlds through any number of edits — is
// anonymous-observable, before or after publication, except the finally
// declassified publish value.
//
// The two configurations differ in one constant:
//   SEARCH_INDEXES_DRAFTS = false  -> safe: search covers published only
//   SEARCH_INDEXES_DRAFTS = true   -> leaky: search counts match drafts
//     too — a classic real-world leak (private data reachable through a
//     search/count side channel) that per-request authorization checks do
//     NOT catch: every individual request is properly authorized, yet the
//     result count differs between the two worlds, distinguishing secrets.

module cms_ni {
  const SEARCH_INDEXES_DRAFTS: bool

  pure val ARTICLES = Set(1, 2)
  pure val VALUES = Set(1, 2)      // abstracted article contents

  pure val DRAFT = 0
  pure val PUBLISHED = 2

  // Article lifecycle state is public and identical in both worlds by
  // construction (public inputs are synchronized), so it is one shared map.
  var artState: int -> int
  // Contents in the two worlds; drafts may diverge (secret inputs).
  var cL: int -> int
  var cR: int -> int

  action init = all {
    artState' = ARTICLES.mapBy(a => DRAFT),
    cL' = ARTICLES.mapBy(a => 1),
    cR' = ARTICLES.mapBy(a => 1),
  }

  // An author edits a draft. SECRET input: the two worlds may write
  // different values (this is where the executions diverge).
  action writeDraft = {
    nondet a = ARTICLES.oneOf()
    nondet vL = VALUES.oneOf()
    nondet vR = VALUES.oneOf()
    all {
      artState.get(a) == DRAFT,
      cL' = cL.set(a, vL),
      cR' = cR.set(a, vR),
      artState' = artState,
    }
  }

  // Publication declassifies: the published text is a PUBLIC input, the
  // same in both worlds from this moment on.
  action publish = {
    nondet a = ARTICLES.oneOf()
    nondet v = VALUES.oneOf()
    all {
      artState.get(a) == DRAFT,
      artState' = artState.set(a, PUBLISHED),
      cL' = cL.set(a, v),
      cR' = cR.set(a, v),
    }
  }

  action step = any { writeDraft, publish }

  // ---- Anonymous observations ---------------------------------------------

  // What an anonymous GET of article a returns in world with contents c:
  // the state is public; the body only when published (else a uniform 404).
  def obsGet(c: int -> int, a: int): (int, int) =
    if (artState.get(a) == PUBLISHED) (200, c.get(a)) else (404, -1)

  // Anonymous search-by-content: how many articles match value v.
  def searchCount(c: int -> int, v: int): int =
    ARTICLES.filter(a =>
      and {
        or { SEARCH_INDEXES_DRAFTS, artState.get(a) == PUBLISHED },
        c.get(a) == v,
      }).size()

  // The hyperproperty, expressed on the composed state: every anonymous
  // observation is identical in the two worlds.
  val obsEqual = and {
    ARTICLES.forall(a => obsGet(cL, a) == obsGet(cR, a)),
    VALUES.forall(v => searchCount(cL, v) == searchCount(cR, v)),
  }

  // ---- Inductive invariant (any-depth proof for the safe config) ----------

  val indShape = and {
    artState.in(setOfMaps(ARTICLES, Set(DRAFT, PUBLISHED))),
    cL.in(setOfMaps(ARTICLES, VALUES)),
    cR.in(setOfMaps(ARTICLES, VALUES)),
  }

  // Strengthening: published contents agree — everything else follows.
  val indInv = and {
    indShape,
    ARTICLES.forall(a => (artState.get(a) == PUBLISHED) implies cL.get(a) == cR.get(a)),
  }
}

module cms_ni_safe {
  import cms_ni(SEARCH_INDEXES_DRAFTS = false).*
}

module cms_ni_leaky {
  import cms_ni(SEARCH_INDEXES_DRAFTS = true).*
}
