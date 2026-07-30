//! The `authz` boundary API.
//!
//! Motivation (research/09-bridging-the-gap.md, Track D episode log): Track
//! D proved a Dafny `Authorize` kernel and embedded it in a Go demo, but
//! flagged a standing caveat -- "nothing forces the app to route through
//! the kernel (the boundary problem)". This module is the fix for the Rust
//! side: instead of the app calling a pure decision function and then
//! being trusted to act on the answer (a convention -- nothing stops a
//! handler from skipping the call, or calling it and ignoring `Err`), the
//! app can only reach the code that performs a protected operation by
//! presenting a `Grant<Op>` value, and the *only* way to produce a
//! `Grant<Op>` is [`require`], which internally calls the proven
//! [`crate::authorize`] (or, for `Submit`, [`crate::can_submit`]).
//!
//! ## What is type-enforced (a compiler error, not a convention)
//!
//! - A handler that needs to perform `Op` (`View`/`Edit`/`Submit`/
//!   `Publish`) on an article MUST hold a value of type `Grant<Op>` to do
//!   so -- see `app/server/src/main.rs`, where every one of the four
//!   protected handlers calls `authz::require::<Op>(...)?` before touching
//!   the article.
//! - `Grant<Op>` cannot be constructed anywhere outside this module: its
//!   only field is private (not `pub`), and the struct itself is
//!   `#[non_exhaustive]`, so even a caller who knows the field name cannot
//!   write a struct-literal from another crate (or another module in this
//!   one). There is no `Default`, no `pub fn new`, no `unsafe` escape
//!   hatch. The only route to a value of this type is a successful call to
//!   `require`.
//! - `require::<Op>` is itself only implementable for the four sealed
//!   marker types below (`Operation` extends a private `Sealed` trait), so
//!   an app author can't define their own `struct MyOp;` and hand-wave a
//!   `Grant<MyOp>` into existence by implementing the trait themselves.
//! - A `Grant<Edit>` cannot be used where a `Grant<Publish>` is required
//!   (or vice versa) -- the type parameter is part of the type, so
//!   "I checked SOME permission" doesn't satisfy "I checked THIS one".
//!
//! `tests/compile_fail.rs` (via `trybuild`) pins down the actual compiler
//! errors for both failure modes (forging a `Grant` directly, and passing
//! the wrong `Grant<Op>` to a function). See `proof-spike/README.md` for
//! the captured `rustc` output.
//!
//! ## What remains convention (not type-enforced)
//!
//! - **Identity freshness.** `require` decides correctly on whatever
//!   `Identity` it is handed -- it has no way to know whether the caller's
//!   `role`/`active` fields are a live re-read or a stale cached snapshot.
//!   That's `AUTH_MODE`'s whole territory (`app/server/src/main.rs`,
//!   `resolve_identity`): the kernel is not, and cannot be, a fix for a
//!   TOCTOU race in how the *caller* obtained the identity it hands in.
//!   This mirrors the formal model's `CHECK_AT_ACTION` split exactly -- see
//!   `app/README.md` and `proof-spike/README.md` "Track D follow-up".
//! - **A handler could call `require`, get `Err`, and ignore it** (e.g.
//!   `let _ = authz::require::<Publish>(...);` without the `?`). Nothing
//!   about the type system stops a handler from discarding a `Result`.
//!   `app/boundary_lint.sh` greps for this shape as a belt-and-suspenders
//!   check (does the handler call `authz::require` AND does it contain no
//!   direct `Role::` comparison of its own), but that is textual pattern
//!   matching, not a proof -- a sufficiently determined rewrite that keeps
//!   the right-looking call in the source while defeating it at runtime
//!   (an early return, a `#[allow]`'d unused-result, etc.) would not be
//!   caught. The `Grant<Op>` typestate is the actual guarantee; the lint is
//!   the "and also we checked" layer.
//! - **Admin user-management** (`admin_deactivate`/`admin_demote` in
//!   main.rs) is deliberately *out of scope* for this refactor -- the task
//!   was view/edit/submit/publish. Those two handlers still do their own
//!   `role != Role::Admin` check and are the one place left in main.rs
//!   where a raw role comparison legitimately remains. `boundary_lint.sh`
//!   does not scan them, and says so.

use crate::{authorize, can_submit, ArticleState, Perms, Role};
use std::marker::PhantomData;

/// Everything the kernel needs to know about the acting principal. The
/// caller (`app/server/src/main.rs`) is responsible for resolving this --
/// including the `AUTH_MODE=cached|live` choice of *which* snapshot to
/// trust (see `resolve_identity`) -- but not for deciding what it means;
/// that's this module's job.
#[derive(Clone, Copy, Debug)]
pub struct Identity {
    pub role: Role,
    pub is_author: bool,
    pub active: bool,
}

/// Everything the kernel needs to know about the target article.
#[derive(Clone, Copy, Debug)]
pub struct ArticleMeta {
    pub state: ArticleState,
}

/// The specific `inv_*` rule (named exactly as in
/// `examples/cms/invariants/cms-security.yaml`) that a denied request
/// violated. This is the machine-readable counterexample hook the app's
/// 403 JSON body reports, now sourced from the kernel instead of hand-typed
/// at each call site.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeniedRule(&'static str);

impl DeniedRule {
    pub fn rule_name(&self) -> &'static str {
        self.0
    }
}

impl std::fmt::Display for DeniedRule {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}

/// Marker types selecting which protected operation is being requested.
/// Zero-sized; they exist only to parameterize `Grant<Op>` / `Operation`.
pub struct View;
pub struct Edit;
pub struct Submit;
pub struct Publish;

mod sealed {
    pub trait Sealed {}
    impl Sealed for super::View {}
    impl Sealed for super::Edit {}
    impl Sealed for super::Submit {}
    impl Sealed for super::Publish {}
}

/// What each operation needs from the decision core to grant or deny, and
/// which rule name to report on denial. Sealed (extends a private trait in
/// an inaccessible module) so only the four marker types above can ever
/// implement it -- an app author cannot invent a fifth operation and grant
/// themselves a `Grant<MyOp>`.
pub trait Operation: sealed::Sealed {
    #[doc(hidden)]
    fn decide(identity: Identity, meta: ArticleMeta) -> Result<(), DeniedRule>;
}

impl Operation for View {
    // main.rs (pre-refactor) 296-310: the `can_view` match plus the rule
    // picked per article state on denial.
    fn decide(identity: Identity, meta: ArticleMeta) -> Result<(), DeniedRule> {
        let Identity { role, is_author, active } = identity;
        let perms: Perms = authorize(role, is_author, active, meta.state);
        if perms.view {
            Ok(())
        } else {
            Err(DeniedRule(match meta.state {
                ArticleState::Draft | ArticleState::InReview => "inv_draft_visibility",
                ArticleState::Archived => "inv_archived_not_public",
                // Unreachable in practice (published is always viewable --
                // inv_published_is_public) but kept for the same reason the
                // pre-refactor main.rs kept it: total match, no panic path.
                ArticleState::Published => "inv_anonymous_published_only",
            }))
        }
    }
}

impl Operation for Edit {
    // main.rs (pre-refactor) 349-366: active gate, then the is_author/
    // editor/admin gate, then the author-only unpublished-work gate.
    // `perms.edit` already ANDs all three together (see `authorize`); the
    // job here is reconstructing *which* one failed, for the 403 body.
    fn decide(identity: Identity, meta: ArticleMeta) -> Result<(), DeniedRule> {
        let Identity { role, is_author, active } = identity;
        let perms = authorize(role, is_author, active, meta.state);
        if !active {
            return Err(DeniedRule("inv_deactivated_does_nothing"));
        }
        if perms.edit {
            return Ok(());
        }
        // active is true and perms.edit is false. Either the base gate
        // (is_author || editor || admin) failed -- inv_edit_rights -- or
        // the base gate passed via `role == Author && is_author` and the
        // unpublished-only exclusion fired -- inv_authors_edit_unpublished_only.
        // Whenever role == Author && is_author, the base gate is
        // necessarily satisfied (is_author alone satisfies it), so
        // perms.edit being false in that case can only be the exclusion.
        if role == Role::Author && is_author {
            Err(DeniedRule("inv_authors_edit_unpublished_only"))
        } else {
            Err(DeniedRule("inv_edit_rights"))
        }
    }
}

impl Operation for Submit {
    // main.rs (pre-refactor) 384-395: active gate, ownership gate, draft-only
    // gate. Not one of the 9 output-facing YAML rules (see `can_submit`'s
    // doc comment) -- reuses `inv_edit_rights` / `inv_publish_from_review_only`
    // as its denial vocabulary, exactly as the pre-refactor app did.
    fn decide(identity: Identity, meta: ArticleMeta) -> Result<(), DeniedRule> {
        let Identity { is_author, active, .. } = identity;
        if !active {
            return Err(DeniedRule("inv_deactivated_does_nothing"));
        }
        if !is_author {
            return Err(DeniedRule("inv_edit_rights"));
        }
        if can_submit(is_author, active, meta.state) {
            Ok(())
        } else {
            Err(DeniedRule("inv_publish_from_review_only"))
        }
    }
}

impl Operation for Publish {
    // main.rs (pre-refactor) 410-419: active gate, editor/admin gate,
    // in-review-only gate.
    fn decide(identity: Identity, meta: ArticleMeta) -> Result<(), DeniedRule> {
        let Identity { role, is_author, active } = identity;
        let perms = authorize(role, is_author, active, meta.state);
        if !active {
            return Err(DeniedRule("inv_deactivated_does_nothing"));
        }
        if !(role == Role::Editor || role == Role::Admin) {
            return Err(DeniedRule("inv_publish_staff_only"));
        }
        if perms.publish {
            Ok(())
        } else {
            Err(DeniedRule("inv_publish_from_review_only"))
        }
    }
}

/// A capability to perform `Op` against the article state it was checked
/// against. This is the sealed token: it has exactly one private field, is
/// marked `#[non_exhaustive]` on top of that, and there is no public
/// constructor other than [`require`]. No code outside this module -- and
/// in particular, no code in `app/server`, which lives in an entirely
/// different crate -- can write a `Grant { .. }` literal, `unsafe`-transmute
/// one into existence (well, they *could* reach for `unsafe`/`transmute`,
/// which no type system stops; that is a deliberately out-of-scope
/// escape hatch, not a gap in this design), or otherwise obtain one except
/// by asking the kernel. See `tests/compile_fail.rs` for the compiler
/// error this produces when attempted.
#[non_exhaustive]
pub struct Grant<Op> {
    _op: PhantomData<Op>,
}

/// The kernel's one and only entry point. Decides whether `identity` may
/// perform `Op` against `meta`, by calling the proven decision core
/// ([`crate::authorize`] for View/Edit/Publish, [`crate::can_submit`] for
/// Submit -- see each `Operation` impl above for the exact mapping). On
/// success, returns a `Grant<Op>` -- proof, checked by the compiler at
/// every call site that needs one, that this decision was actually made.
/// On denial, returns the specific violated `inv_*` rule.
pub fn require<Op: Operation>(identity: Identity, meta: ArticleMeta) -> Result<Grant<Op>, DeniedRule> {
    Op::decide(identity, meta)?;
    Ok(Grant { _op: PhantomData })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ident(role: Role, is_author: bool, active: bool) -> Identity {
        Identity { role, is_author, active }
    }

    #[test]
    fn require_view_matches_authorize() {
        for (role, is_author, active, state) in crate::all_inputs() {
            if role == Role::Anonymous && is_author {
                continue;
            }
            let perms = authorize(role, is_author, active, state);
            let got = require::<View>(ident(role, is_author, active), ArticleMeta { state });
            assert_eq!(got.is_ok(), perms.view, "View mismatch at ({role:?}, {is_author}, {active}, {state:?})");
        }
    }

    #[test]
    fn require_edit_matches_authorize() {
        for (role, is_author, active, state) in crate::all_inputs() {
            if role == Role::Anonymous && is_author {
                continue;
            }
            let perms = authorize(role, is_author, active, state);
            let got = require::<Edit>(ident(role, is_author, active), ArticleMeta { state });
            assert_eq!(got.is_ok(), perms.edit, "Edit mismatch at ({role:?}, {is_author}, {active}, {state:?})");
        }
    }

    #[test]
    fn require_publish_matches_authorize() {
        for (role, is_author, active, state) in crate::all_inputs() {
            if role == Role::Anonymous && is_author {
                continue;
            }
            let perms = authorize(role, is_author, active, state);
            let got = require::<Publish>(ident(role, is_author, active), ArticleMeta { state });
            assert_eq!(got.is_ok(), perms.publish, "Publish mismatch at ({role:?}, {is_author}, {active}, {state:?})");
        }
    }

    #[test]
    fn require_submit_matches_can_submit() {
        const STATES: [ArticleState; 4] =
            [ArticleState::Draft, ArticleState::InReview, ArticleState::Published, ArticleState::Archived];
        for role in [Role::Anonymous, Role::Author, Role::Editor, Role::Admin] {
            for is_author in [false, true] {
                if role == Role::Anonymous && is_author {
                    continue;
                }
                for active in [false, true] {
                    for state in STATES {
                        let expected = can_submit(is_author, active, state);
                        let got = require::<Submit>(ident(role, is_author, active), ArticleMeta { state });
                        assert_eq!(
                            got.is_ok(),
                            expected,
                            "Submit mismatch at ({role:?}, {is_author}, {active}, {state:?})"
                        );
                    }
                }
            }
        }
    }

    /// The denial rule reported must always be one of the 9 named YAML
    /// rules (or, for Submit, one of the two it legitimately reuses) --
    /// never an empty/garbage string. Cheap sanity net around the manual
    /// if/else reconstruction in each `Operation::decide`.
    #[test]
    fn denial_rules_are_always_named() {
        const KNOWN: &[&str] = &[
            "inv_draft_visibility",
            "inv_archived_not_public",
            "inv_anonymous_published_only",
            "inv_deactivated_does_nothing",
            "inv_authors_edit_unpublished_only",
            "inv_edit_rights",
            "inv_publish_staff_only",
            "inv_publish_from_review_only",
        ];
        for (role, is_author, active, state) in crate::all_inputs() {
            if role == Role::Anonymous && is_author {
                continue;
            }
            for err in [
                require::<View>(ident(role, is_author, active), ArticleMeta { state }).err(),
                require::<Edit>(ident(role, is_author, active), ArticleMeta { state }).err(),
                require::<Publish>(ident(role, is_author, active), ArticleMeta { state }).err(),
                require::<Submit>(ident(role, is_author, active), ArticleMeta { state }).err(),
            ] {
                if let Some(d) = err {
                    assert!(KNOWN.contains(&d.rule_name()), "unknown denial rule {:?}", d.rule_name());
                }
            }
        }
    }
}
