// authz.dfy
//
// Track D — "requirements -> proven code" (see research/09-bridging-the-gap.md).
//
// The ten rules in examples/cms/invariants/cms-security.yaml describe one
// access decision: given a viewer (role, activity flag, author relationship)
// and an article's lifecycle state, is view/edit/publish allowed?
//
// This file inverts the usual test relationship. Instead of writing decision
// logic and then writing tests that sample some inputs and check the rules
// hold, the ten rules are written ONCE as `ensures` clauses on the Authorize
// function below, and the Dafny verifier proves — for every possible input,
// not just sampled ones — that the implementation satisfies every rule.
// `dafny verify` is the proof; `check.sh` re-runs it on every edit.
//
// Each ensures clause below is commented with the YAML invariant name it
// encodes, and the English sentence is copied from cms-security.yaml so the
// mapping YAML -> ensures can be read side by side with the source of truth.
// That mapping is human-drafted and human-reviewed — it is the one part of
// this pipeline that is NOT machine-checked. See README.md, "What's proven
// vs what's trusted."

module Authz {

  datatype Role = Anonymous | Author | Editor | Admin

  datatype ArticleState = Draft | InReview | Published | Archived

  // Bundles the three yes/no outputs the YAML schema calls can_view,
  // can_edit, can_publish.
  datatype Decision = Decision(view: bool, edit: bool, publish: bool)

  // The decision kernel.
  //
  // Inputs mirror the YAML `variables` block exactly:
  //   role            <-> viewer_role
  //   isAuthor        <-> viewer_is_author
  //   active          <-> viewer_active
  //   state           <-> article_state
  // (session_ttl_minutes is not decided by this function; it belongs to a
  // session-layer concern the YAML groups with the access rules but that
  // this kernel does not model — see README.)
  //
  // isAuthor is only meaningful for Role.Author; a precondition forces
  // callers to keep that combination consistent, which is how the kernel
  // proves inv_anonymous_never_author without ever inspecting isAuthor
  // itself for non-authors.
  function Authorize(role: Role, isAuthor: bool, active: bool, state: ArticleState): (d: Decision)
    // An anonymous viewer is never "the author" of anything (isAuthor makes
    // no sense to set true for a role other than Author) — this keeps the
    // model consistent with inv_anonymous_never_author without needing a
    // separate viewer-identity type.
    requires role != Author ==> !isAuthor

    // --- inv_published_is_public ---
    // "Published articles are publicly readable by everyone, including
    // logged-out visitors."
    ensures state == Published ==> d.view

    // --- inv_anonymous_published_only ---
    // "Anonymous visitors can read published articles and nothing else."
    ensures (role == Anonymous && d.view) ==> state == Published

    // --- inv_draft_visibility ---
    // "A draft is visible only to its author, editors, and admins."
    ensures (state == Draft && d.view) ==> (isAuthor || role == Editor || role == Admin)

    // --- inv_publish_staff_only ---
    // "Only editors and admins may publish."
    ensures d.publish ==> (role == Editor || role == Admin)

    // --- inv_publish_from_review_only ---
    // "An article can only be published out of the in-review state — never
    // straight from draft."
    ensures d.publish ==> state == InReview

    // --- inv_edit_rights ---
    // "Editing requires being the author, an editor, or an admin."
    ensures d.edit ==> (isAuthor || role == Editor || role == Admin)

    // --- inv_authors_edit_unpublished_only ---
    // "Authors may edit their articles only before publication (draft or
    // in-review); after that, changes go through an editor."
    ensures (d.edit && role == Author) ==> (state == Draft || state == InReview)

    // --- inv_deactivated_does_nothing ---
    // "A deactivated account can neither edit nor publish anything."
    ensures !active ==> (!d.edit && !d.publish)

    // --- inv_archived_not_public ---
    // "Archived articles are kept for staff reference and are not publicly
    // accessible."
    ensures (state == Archived && d.view) ==> role != Anonymous

    // --- inv_anonymous_never_author ---
    // "An anonymous visitor is by definition not the author of anything."
    // (Encoded structurally: Authorize can only be called with isAuthor
    // true when role == Author, so an Anonymous viewer can never reach
    // isAuthor == true. This clause restates it as an explicit, checkable
    // postcondition so it stays visible in the proof obligation list
    // instead of hiding in the precondition.)
    ensures role == Anonymous ==> !isAuthor

    // --- FEATURES (not in the YAML; without these the rules above are
    // satisfiable by "always deny everything", which would verify but be
    // useless). These pin down that the kernel actually grants access when
    // it is supposed to, mirroring the safety+features split used
    // elsewhere in this project. ---

    // An active editor or admin can view a draft (staff visibility isn't
    // just "not forbidden", it is guaranteed).
    ensures (active && (role == Editor || role == Admin) && state == Draft) ==> d.view

    // An active editor or admin can publish an in-review article.
    ensures (active && (role == Editor || role == Admin) && state == InReview) ==> d.publish

    // An active author can view and edit their own draft or in-review
    // article.
    ensures (active && role == Author && isAuthor && (state == Draft || state == InReview))
            ==> (d.view && d.edit)

    // Everyone (including a logged-out visitor) can view a published
    // article — the public-read guarantee, not just "not blocked".
    ensures state == Published ==> d.view
  {
    // --- view ---
    var view :=
      if state == Published then true
      else if state == Archived then role != Anonymous  // staff-only, any staff role, regardless of active/author
      else if state == Draft || state == InReview then
        isAuthor || role == Editor || role == Admin
      else
        false;

    // --- edit ---
    // Deactivated accounts never get edit rights, full stop.
    var edit :=
      if !active then false
      else if role == Editor || role == Admin then
        // staff may edit in any state (only "authors" are restricted to
        // pre-publication editing by inv_authors_edit_unpublished_only)
        true
      else if role == Author && isAuthor then
        state == Draft || state == InReview
      else
        false;

    // --- publish ---
    var publish :=
      if !active then false
      else if role == Editor || role == Admin then
        state == InReview
      else
        false;

    Decision(view, edit, publish)
  }

}
