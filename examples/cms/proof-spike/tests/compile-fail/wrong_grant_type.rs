// A caller who legitimately obtained a Grant -- but for the wrong
// operation -- tries to use it where a `Grant<Publish>` is required. This
// is the "checked SOME permission, not THIS one" failure mode: having
// *any* Grant<Op> is not enough, it must be the Grant<Op> for the
// operation being performed. Must fail to compile with a type mismatch.
use authz_spike::authz::{require, ArticleMeta, Edit, Grant, Identity, Publish};
use authz_spike::{ArticleState, Role};

fn do_publish(_grant: Grant<Publish>) {
    // ... would flip the article to Published here ...
}

fn main() {
    let identity = Identity {
        role: Role::Editor,
        is_author: false,
        active: true,
    };
    let meta = ArticleMeta {
        state: ArticleState::InReview,
    };

    // This succeeds -- eve really can edit this article -- but it proves
    // nothing about *publishing* it.
    let edit_grant: Grant<Edit> = require(identity, meta).unwrap();

    do_publish(edit_grant); // expected `Grant<Publish>`, found `Grant<Edit>`
}
