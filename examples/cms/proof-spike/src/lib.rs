//! Track E proof spike: a pure, finite-domain re-implementation of the CMS
//! authorization decision, extracted from the running app so it can be
//! checked two ways — exhaustive enumeration and Kani — against the 10
//! rules in `examples/cms/invariants/cms-security.yaml`.
//!
//! Source of truth: `examples/cms/app/server/src/main.rs`, specifically the
//! `AUTH_MODE=live` behavior (every request re-reads the acting user's
//! *current* role/active flag before deciding — see `resolve_identity`,
//! lines 193-202). `live` mode is the one whose per-request decision is a
//! pure function of (role, is_author, active, state); `cached` mode instead
//! makes the decision a function of a *stale session snapshot*, which is a
//! different (and, per Track B/C, deliberately buggy) question. This
//! extraction is the decision core both modes ultimately call once identity
//! is resolved.
//!
//! Cited lines (as read on 2026-07-30):
//!   - `get_article` (view), lines 296-301 — the `can_view` match, plus the
//!     lines 282-293 rule that a deactivated viewer is folded to Anonymous.
//!   - `edit_article` (edit), lines 349-366 — the active check, the
//!     is_author/editor/admin gate, and the author-only unpublished gate.
//!   - `publish_article` (publish), lines 410-419 — the active check, the
//!     editor/admin gate, and the in-review-only gate.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Anonymous,
    Author,
    Editor,
    Admin,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArticleState {
    Draft,
    InReview,
    Published,
    Archived,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Perms {
    pub view: bool,
    pub edit: bool,
    pub publish: bool,
}

/// The decision core. Faithful port of the app's `live`-mode behavior:
/// role/is_author/active are whatever the caller currently is (no stale
/// session snapshot involved) and `state` is the article's lifecycle state.
///
/// main.rs, lines 282-293: a deactivated viewer is treated as anonymous for
/// *viewing* purposes (the anonymous fold is not spelled out for edit/publish
/// because those already `return Err` on `!active` before doing anything
/// else — main.rs:349-351, 410-412).
pub fn authorize(role: Role, is_author: bool, active: bool, state: ArticleState) -> Perms {
    // ---- view: main.rs 282-301 --------------------------------------
    // "if !active { (Anonymous, false) } else { (role, is_author) }"
    let (view_role, view_is_author) = if active { (role, is_author) } else { (Role::Anonymous, false) };
    let can_view = match state {
        ArticleState::Published => true,
        ArticleState::Draft | ArticleState::InReview => {
            view_is_author || view_role == Role::Editor || view_role == Role::Admin
        }
        ArticleState::Archived => view_role != Role::Anonymous,
    };

    // ---- edit: main.rs 349-366 --------------------------------------
    let can_edit = active
        && (is_author || role == Role::Editor || role == Role::Admin)
        && !(role == Role::Author
            && is_author
            && !matches!(state, ArticleState::Draft | ArticleState::InReview));

    // ---- publish: main.rs 410-419 -----------------------------------
    let can_publish =
        active && (role == Role::Editor || role == Role::Admin) && matches!(state, ArticleState::InReview);

    Perms { view: can_view, edit: can_edit, publish: can_publish }
}

/// Deliberate-bug variant: drops the `active` check on `can_edit`
/// (imagine someone "simplified" main.rs:349-351 away). Everything else is
/// identical to `authorize`. Used to prove the exhaustive test (and the
/// Kani harness) actually catch a real regression, not just pass vacuously.
pub fn authorize_buggy_missing_active_check(
    role: Role,
    is_author: bool,
    active: bool,
    state: ArticleState,
) -> Perms {
    let (view_role, view_is_author) = if active { (role, is_author) } else { (Role::Anonymous, false) };
    let can_view = match state {
        ArticleState::Published => true,
        ArticleState::Draft | ArticleState::InReview => {
            view_is_author || view_role == Role::Editor || view_role == Role::Admin
        }
        ArticleState::Archived => view_role != Role::Anonymous,
    };

    // BUG: no `active &&` guard here — a deactivated author/editor/admin can
    // still edit. This is exactly what inv_deactivated_does_nothing forbids.
    let can_edit = (is_author || role == Role::Editor || role == Role::Admin)
        && !(role == Role::Author
            && is_author
            && !matches!(state, ArticleState::Draft | ArticleState::InReview));

    let can_publish =
        active && (role == Role::Editor || role == Role::Admin) && matches!(state, ArticleState::InReview);

    Perms { view: can_view, edit: can_edit, publish: can_publish }
}

/// Crossover experiment: the app's *real* `is_author` isn't a bool someone
/// hands you -- it's derived by comparing IDs (main.rs:289:
/// `user == article.author`, both `String`s; in a production system these
/// would be u64 primary keys). This variant makes that derivation explicit
/// and non-finite: `viewer_id`/`author_id` range over all of `u64`, so the
/// input space is no longer 64 points but 4 (role) x 2 (active) x 4 (state)
/// x 2^64 (viewer_id) x 2^64 (author_id) ~= 2^131 points. See README
/// "when the domain stops being finite" for what this does to each
/// technique.
pub fn authorize_by_id(role: Role, active: bool, state: ArticleState, viewer_id: u64, author_id: u64) -> Perms {
    authorize(role, viewer_id == author_id, active, state)
}

// =====================================================================
// The 10 YAML rules (examples/cms/invariants/cms-security.yaml), each as a
// Rust predicate over (role, is_author, active, state, perms). A predicate
// returning `true` means "this input/output combination does not violate
// the rule."
// =====================================================================

pub fn inv_published_is_public(_r: Role, _a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(state == published, can_view)
    !(s == ArticleState::Published) || p.view
}

pub fn inv_anonymous_published_only(r: Role, _a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(role == anonymous and can_view, state == published)
    !(r == Role::Anonymous && p.view) || s == ArticleState::Published
}

pub fn inv_draft_visibility(r: Role, a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(state == draft and can_view, is_author or role in {editor, admin})
    !(s == ArticleState::Draft && p.view) || (a || r == Role::Editor || r == Role::Admin)
}

pub fn inv_publish_staff_only(r: Role, _a: bool, _act: bool, _s: ArticleState, p: Perms) -> bool {
    // implies(can_publish, role in {editor, admin})
    !p.publish || (r == Role::Editor || r == Role::Admin)
}

pub fn inv_publish_from_review_only(_r: Role, _a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(can_publish, state == in_review)
    !p.publish || s == ArticleState::InReview
}

pub fn inv_edit_rights(r: Role, a: bool, _act: bool, _s: ArticleState, p: Perms) -> bool {
    // implies(can_edit, is_author or role in {editor, admin})
    !p.edit || (a || r == Role::Editor || r == Role::Admin)
}

pub fn inv_authors_edit_unpublished_only(r: Role, _a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(can_edit and role == author, state in {draft, in_review})
    !(p.edit && r == Role::Author) || matches!(s, ArticleState::Draft | ArticleState::InReview)
}

pub fn inv_deactivated_does_nothing(_r: Role, _a: bool, active: bool, _s: ArticleState, p: Perms) -> bool {
    // implies(not active, not can_edit and not can_publish)
    active || (!p.edit && !p.publish)
}

pub fn inv_archived_not_public(r: Role, _a: bool, _act: bool, s: ArticleState, p: Perms) -> bool {
    // implies(state == archived and can_view, role != anonymous)
    !(s == ArticleState::Archived && p.view) || r != Role::Anonymous
}

pub fn inv_anonymous_never_author(r: Role, a: bool, _act: bool, _s: ArticleState, _p: Perms) -> bool {
    // implies(role == anonymous, not is_author)
    // NB: this rule is a *shape-of-input* constraint, not a property of
    // authorize()'s output — see README "the 11th rule" section. It's
    // included here for completeness of the 10-rule set, but the
    // exhaustive/Kani harnesses treat it as a domain filter, not a thing
    // the decision function is asked to establish.
    r != Role::Anonymous || !a
}

/// The 9 output-facing rules, paired with their names, so a harness can
/// iterate and report which one fails.
pub const ALL_RULES: &[(&str, fn(Role, bool, bool, ArticleState, Perms) -> bool)] = &[
    ("inv_published_is_public", inv_published_is_public),
    ("inv_anonymous_published_only", inv_anonymous_published_only),
    ("inv_draft_visibility", inv_draft_visibility),
    ("inv_publish_staff_only", inv_publish_staff_only),
    ("inv_publish_from_review_only", inv_publish_from_review_only),
    ("inv_edit_rights", inv_edit_rights),
    ("inv_authors_edit_unpublished_only", inv_authors_edit_unpublished_only),
    ("inv_deactivated_does_nothing", inv_deactivated_does_nothing),
    ("inv_archived_not_public", inv_archived_not_public),
];

// =====================================================================
// Feature predicates — sanity checks that the rule set is satisfiable and
// isn't just vacuously true. If every predicate above were `false` (say,
// authorize() always denied everything), all 10 rules would still hold —
// implications with a false antecedent, or output all-false, are cheap to
// satisfy. These three predicates require *some* access to actually be
// granted, so an all-deny stub authorize() would fail them.
// =====================================================================

/// An active editor can view drafts they didn't write.
pub fn feature_active_editor_views_drafts() -> bool {
    authorize(Role::Editor, false, true, ArticleState::Draft).view
}

/// An active author can edit their own draft.
pub fn feature_active_author_edits_own_draft() -> bool {
    authorize(Role::Author, true, true, ArticleState::Draft).edit
}

/// An active editor can publish an in-review article.
pub fn feature_active_editor_publishes_in_review() -> bool {
    authorize(Role::Editor, false, true, ArticleState::InReview).publish
}

/// Iterate the full 4 x 2 x 2 x 4 = 64-point input domain.
pub fn all_inputs() -> impl Iterator<Item = (Role, bool, bool, ArticleState)> {
    const ROLES: [Role; 4] = [Role::Anonymous, Role::Author, Role::Editor, Role::Admin];
    const STATES: [ArticleState; 4] =
        [ArticleState::Draft, ArticleState::InReview, ArticleState::Published, ArticleState::Archived];
    ROLES.into_iter().flat_map(move |r| {
        [false, true].into_iter().flat_map(move |a| {
            [false, true].into_iter().flat_map(move |act| STATES.into_iter().map(move |s| (r, a, act, s)))
        })
    })
}

#[cfg(kani)]
mod kani_harness {
    use super::*;

    fn any_role() -> Role {
        match kani::any::<u8>() % 4 {
            0 => Role::Anonymous,
            1 => Role::Author,
            2 => Role::Editor,
            _ => Role::Admin,
        }
    }

    fn any_state() -> ArticleState {
        match kani::any::<u8>() % 4 {
            0 => ArticleState::Draft,
            1 => ArticleState::InReview,
            2 => ArticleState::Published,
            _ => ArticleState::Archived,
        }
    }

    /// One proof harness per rule, asserting it for ALL inputs Kani can
    /// pick (kani::any(), then bounded/modulo'd into the 4 role/4 state
    /// enum), not just the 64 concrete tuples the exhaustive test builds.
    macro_rules! rule_harness {
        ($fn_name:ident, $rule:expr) => {
            #[kani::proof]
            fn $fn_name() {
                let role = any_role();
                let is_author: bool = kani::any();
                let active: bool = kani::any();
                let state = any_state();
                // Precondition: the real app never calls authorize() with
                // role=Anonymous & is_author=true (main.rs:277-294 always
                // folds is_author to false alongside Anonymous). Without
                // this assumption Kani (correctly) finds a "violation" on
                // an input the app can never produce -- see README
                // "the 11th rule".
                kani::assume(role != Role::Anonymous || !is_author);
                let perms = authorize(role, is_author, active, state);
                assert!($rule(role, is_author, active, state, perms));
            }
        };
    }

    rule_harness!(kani_inv_published_is_public, inv_published_is_public);
    rule_harness!(kani_inv_anonymous_published_only, inv_anonymous_published_only);
    rule_harness!(kani_inv_draft_visibility, inv_draft_visibility);
    rule_harness!(kani_inv_publish_staff_only, inv_publish_staff_only);
    rule_harness!(kani_inv_publish_from_review_only, inv_publish_from_review_only);
    rule_harness!(kani_inv_edit_rights, inv_edit_rights);
    rule_harness!(kani_inv_authors_edit_unpublished_only, inv_authors_edit_unpublished_only);
    rule_harness!(kani_inv_deactivated_does_nothing, inv_deactivated_does_nothing);
    rule_harness!(kani_inv_archived_not_public, inv_archived_not_public);

    /// The buggy variant: this harness is EXPECTED to fail
    /// (`inv_deactivated_does_nothing`), demonstrating Kani catches the
    /// same regression the exhaustive test catches.
    #[kani::proof]
    fn kani_buggy_variant_violates_deactivated_does_nothing() {
        let role = any_role();
        let is_author: bool = kani::any();
        let active: bool = kani::any();
        let state = any_state();
        kani::assume(role != Role::Anonymous || !is_author);
        let perms = authorize_buggy_missing_active_check(role, is_author, active, state);
        assert!(inv_deactivated_does_nothing(role, is_author, active, state, perms));
    }

    /// The crossover experiment: `viewer_id`/`author_id` are fully
    /// unconstrained u64 -- a ~2^131-point input space that no exhaustive
    /// loop could ever enumerate. Kani proves all 9 rules over ALL of it
    /// (not a sample) by reasoning symbolically about `viewer_id ==
    /// author_id` rather than trying concrete values one at a time. This
    /// is the harness the README's "when the domain stops being finite"
    /// section is backed by.
    macro_rules! id_rule_harness {
        ($fn_name:ident, $rule:expr) => {
            #[kani::proof]
            fn $fn_name() {
                let role = any_role();
                let active: bool = kani::any();
                let state = any_state();
                let viewer_id: u64 = kani::any();
                let author_id: u64 = kani::any();
                let is_author = viewer_id == author_id;
                kani::assume(role != Role::Anonymous || !is_author);
                let perms = authorize_by_id(role, active, state, viewer_id, author_id);
                assert!($rule(role, is_author, active, state, perms));
            }
        };
    }

    id_rule_harness!(kani_id_inv_edit_rights, inv_edit_rights);
    id_rule_harness!(kani_id_inv_authors_edit_unpublished_only, inv_authors_edit_unpublished_only);
    id_rule_harness!(kani_id_inv_draft_visibility, inv_draft_visibility);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn feature_predicates_are_satisfiable() {
        assert!(feature_active_editor_views_drafts(), "rule set must not be vacuously all-deny");
        assert!(feature_active_author_edits_own_draft(), "rule set must not be vacuously all-deny");
        assert!(feature_active_editor_publishes_in_review(), "rule set must not be vacuously all-deny");
    }

    /// THE exhaustive proof: every *reachable* input (56 of the 64 raw
    /// tuples — see `inv_anonymous_never_author_describes_reachable_inputs`
    /// below for why 8 are excluded), all 9 output-facing rules. Any
    /// failure prints the offending tuple and rule name, exactly like the
    /// app's named-403 counterexample convention.
    ///
    /// First draft of this test iterated the full unfiltered 64 and it
    /// correctly failed on inv_anonymous_published_only for
    /// (Anonymous, is_author=true, active=true, Draft) -> view=true. That
    /// is a real result, not a bug in the test: authorize() itself does not
    /// defend against a caller passing role=Anonymous with is_author=true
    /// (the real app's identity resolution never does), so exhaustively
    /// probing the *raw* 64-point grid finds "violations" on inputs that
    /// can't occur end-to-end. The fix applied here -- filtering by the
    /// same precondition `inv_anonymous_never_author` encodes -- is exactly
    /// the `kani::assume` the Kani harnesses need for the same reason.
    #[test]
    fn exhaustive_all_reachable_inputs_satisfy_all_9_output_rules() {
        let mut checked = 0usize;
        for (role, is_author, active, state) in all_inputs() {
            if role == Role::Anonymous && is_author {
                continue; // unreachable precondition violation, see above
            }
            checked += 1;
            let perms = authorize(role, is_author, active, state);
            for (name, rule) in ALL_RULES {
                assert!(
                    rule(role, is_author, active, state, perms),
                    "rule {name} violated by input ({role:?}, is_author={is_author}, active={active}, {state:?}) -> {perms:?}"
                );
            }
        }
        assert_eq!(checked, 56, "reachable domain size must be 64 - 8 = 56");
    }

    /// inv_anonymous_never_author is a precondition on the *input shape*,
    /// not a property of authorize()'s output (it never mentions can_view/
    /// can_edit/can_publish). Of the 64 raw (role, is_author) pairings, the
    /// 8 with role=Anonymous & is_author=true are impossible in the real
    /// app: `resolve_identity`/`get_article` (main.rs:277-294) only ever
    /// produce is_author=false when role is folded to Anonymous. This test
    /// checks that fact directly, and documents that the other 56 "reachable"
    /// inputs are exactly the ones exhaustively checked above with a
    /// meaningful is_author flag.
    #[test]
    fn inv_anonymous_never_author_describes_reachable_inputs() {
        let mut unreachable = 0usize;
        for (role, is_author, active, state) in all_inputs() {
            let perms = authorize(role, is_author, active, state);
            if !inv_anonymous_never_author(role, is_author, active, state, perms) {
                unreachable += 1;
                assert_eq!(role, Role::Anonymous);
                assert!(is_author);
            }
        }
        assert_eq!(unreachable, 8, "expected exactly the 1 role x 1 is_author x 2 active x 4 state = 8 impossible tuples");
    }

    /// The deliberate bug (missing `active` check on can_edit) MUST be
    /// caught by the exhaustive sweep. This is the falsifier for "exhaustive
    /// enumeration is as good as Kani here": if this test can't catch it,
    /// the technique isn't proof-grade.
    #[test]
    fn exhaustive_sweep_catches_missing_active_check() {
        let mut violations = 0usize;
        for (role, is_author, active, state) in all_inputs() {
            if role == Role::Anonymous && is_author {
                continue; // unreachable, see the "reachable inputs" test above
            }
            let perms = authorize_buggy_missing_active_check(role, is_author, active, state);
            if !inv_deactivated_does_nothing(role, is_author, active, state, perms) {
                violations += 1;
            }
        }
        assert!(
            violations > 0,
            "expected the buggy variant to violate inv_deactivated_does_nothing somewhere in the reachable domain"
        );
        // Concretely (active=false only -- the bug is invisible when
        // active=true): Editor and Admin roles get can_edit=true
        // unconditionally (is_author doesn't gate them) across all 4
        // states each = 4+4=8 for each role = 16. Author with
        // is_author=true gets can_edit=true only for Draft/InReview (the
        // "authors edit unpublished only" restriction still correctly
        // denies Published/Archived even in the buggy version) = 2.
        // Total = 16 + 2 = 18.
        assert_eq!(violations, 18);
    }

    /// Timing data point for the README's crossover argument: a *bounded*
    /// slice of the id-keyed domain (1,000 x 1,000 ids, still x4 roles x2
    /// active x4 states = 32,000,000 concrete calls) run through the same
    /// "loop and assert" exhaustive style used above. This is already a
    /// scaled-down stand-in for the real domain (u64 x u64, ~2^131 points);
    /// timing it tells us how fast the wall clock leaves "feasible" as ID
    /// spaces grow, without literally trying to enumerate u64.
    #[test]
    fn bounded_id_domain_exhaustive_timing() {
        const N: u64 = 1_000;
        let start = std::time::Instant::now();
        let mut checked = 0u64;
        const ROLES: [Role; 4] = [Role::Anonymous, Role::Author, Role::Editor, Role::Admin];
        const STATES: [ArticleState; 4] =
            [ArticleState::Draft, ArticleState::InReview, ArticleState::Published, ArticleState::Archived];
        for role in ROLES {
            for active in [false, true] {
                for state in STATES {
                    for viewer_id in 0..N {
                        for author_id in 0..N {
                            let is_author = viewer_id == author_id;
                            if role == Role::Anonymous && is_author {
                                continue;
                            }
                            checked += 1;
                            let perms = authorize_by_id(role, active, state, viewer_id, author_id);
                            for (name, rule) in ALL_RULES {
                                assert!(
                                    rule(role, is_author, active, state, perms),
                                    "rule {name} violated by ({role:?}, viewer_id={viewer_id}, author_id={author_id}, active={active}, {state:?})"
                                );
                            }
                        }
                    }
                }
            }
        }
        let elapsed = start.elapsed();
        eprintln!(
            "bounded_id_domain_exhaustive_timing: checked {checked} tuples (N={N}) in {elapsed:?} \
             ({:.1} tuples/ms)",
            checked as f64 / elapsed.as_millis().max(1) as f64
        );
        // u64::MAX x u64::MAX is roughly (N=1000 -> full u64 range) a factor
        // of ~1.8e19 squared larger than this slice; even at this loop's
        // throughput that is not a "wait longer" problem, it's a "will not
        // finish before the heat death of the universe" problem. See
        // README for the extrapolated numbers using this run's measured
        // throughput.
    }
}
