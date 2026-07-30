// authz_buggy.dfy
//
// A deliberately-seeded copy of authz.dfy: the `ensures` clauses (the ten
// YAML rules + the feature guarantees) are IDENTICAL to authz.dfy. Only the
// implementation changed — one line, one subtle bug:
//
//     publish := if role in {Editor, Admin} then state == InReview else false
//
// dropped the `!active` guard. A deactivated editor or admin can now
// "publish" an in-review article.
//
// This file exists to demonstrate the gate: `dafny verify` must REJECT it,
// and must name the specific ensures clause the implementation can no
// longer satisfy. See README.md, "Buggy variant is rejected" for the
// captured output of running this file through the verifier.

module AuthzBuggy {

  datatype Role = Anonymous | Author | Editor | Admin
  datatype ArticleState = Draft | InReview | Published | Archived
  datatype Decision = Decision(view: bool, edit: bool, publish: bool)

  function Authorize(role: Role, isAuthor: bool, active: bool, state: ArticleState): (d: Decision)
    requires role != Author ==> !isAuthor

    // --- inv_published_is_public ---
    ensures state == Published ==> d.view
    // --- inv_anonymous_published_only ---
    ensures (role == Anonymous && d.view) ==> state == Published
    // --- inv_draft_visibility ---
    ensures (state == Draft && d.view) ==> (isAuthor || role == Editor || role == Admin)
    // --- inv_publish_staff_only ---
    ensures d.publish ==> (role == Editor || role == Admin)
    // --- inv_publish_from_review_only ---
    ensures d.publish ==> state == InReview
    // --- inv_edit_rights ---
    ensures d.edit ==> (isAuthor || role == Editor || role == Admin)
    // --- inv_authors_edit_unpublished_only ---
    ensures (d.edit && role == Author) ==> (state == Draft || state == InReview)
    // --- inv_deactivated_does_nothing ---
    // THIS is the clause the seeded bug violates: a deactivated editor
    // publishing an in-review article now returns publish == true.
    ensures !active ==> (!d.edit && !d.publish)
    // --- inv_archived_not_public ---
    ensures (state == Archived && d.view) ==> role != Anonymous
    // --- inv_anonymous_never_author ---
    ensures role == Anonymous ==> !isAuthor

    // --- features ---
    ensures (active && (role == Editor || role == Admin) && state == Draft) ==> d.view
    ensures (active && (role == Editor || role == Admin) && state == InReview) ==> d.publish
    ensures (active && role == Author && isAuthor && (state == Draft || state == InReview))
            ==> (d.view && d.edit)
    ensures state == Published ==> d.view
  {
    var view :=
      if state == Published then true
      else if state == Archived then role != Anonymous
      else if state == Draft || state == InReview then
        isAuthor || role == Editor || role == Admin
      else
        false;

    var edit :=
      if !active then false
      else if role == Editor || role == Admin then
        true
      else if role == Author && isAuthor then
        state == Draft || state == InReview
      else
        false;

    // BUG: the `!active` guard from authz.dfy was dropped here. Compare to
    // authz.dfy's `publish :=` — that version starts with `if !active then
    // false else ...`; this one goes straight to the role check.
    var publish :=
      if role == Editor || role == Admin then
        state == InReview
      else
        false;

    Decision(view, edit, publish)
  }

}
