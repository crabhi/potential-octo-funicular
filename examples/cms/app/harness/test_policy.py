"""Property tests run against a *live* server (AUTH_MODE=live), i.e. every
request re-reads current role/active state — the intended, non-buggy mode.

Maps onto invariants in examples/cms/invariants/cms-security.yaml:
  (a) inv_anonymous_published_only / inv_archived_not_public / inv_draft_visibility
  (b) inv_edit_rights (an author is never "the author" of someone else's draft)
  (c) inv_publish_from_review_only
  (d) inv_deactivated_does_nothing (via publish)
  (e) inv_publish_staff_only (via demote)

Tests (d) and (e) mutate global admin state (they demote/deactivate eve) and
are therefore ordered last and written to tolerate running after each other.
"""
from hypothesis import given, settings, strategies as st

import cms_client as c

pytestmark = []


# (a) Anonymous GET never returns a non-published article's body.
@given(article_id=st.sampled_from(c.ARTICLE_IDS))
@settings(deadline=None, max_examples=25)
def test_anonymous_never_sees_non_published(article_id):
    resp = c.get_article(article_id, token=None)
    if resp.status_code == 200:
        body = resp.json()
        assert body["state"] == "published", (
            f"anonymous viewer read article {article_id} in state "
            f"{body['state']!r} — violates inv_anonymous_published_only"
        )
    else:
        assert resp.status_code == 403
        rule = c.violated_rule(resp)
        assert rule in ("inv_draft_visibility", "inv_archived_not_public")


# (b) An author can never edit another author's draft.
@given(owner=st.sampled_from(["alice", "bob"]), other=st.sampled_from(["alice", "bob"]))
@settings(deadline=None, max_examples=10)
def test_author_cannot_edit_others_draft(owner, other):
    if owner == other:
        return  # not the scenario under test
    owner_token = c.login(owner)
    other_token = c.login(other)

    created = c.create_article(owner_token, title="mine", body="draft body")
    assert created.status_code == 200
    article_id = created.json()["id"]

    resp = c.edit_article(article_id, other_token, title="hijacked")
    assert resp.status_code == 403, "another author was able to edit this draft"
    assert c.violated_rule(resp) == "inv_edit_rights"


# (c) Publish is always refused unless the article is in_review.
@given(article_id=st.sampled_from([1, 2, 4]))  # published, draft, archived
@settings(deadline=None, max_examples=10)
def test_publish_from_non_review_always_refused(article_id):
    editor_token = c.login("eve")
    resp = c.publish_article(article_id, editor_token)
    assert resp.status_code == 403
    assert c.violated_rule(resp) == "inv_publish_from_review_only"


# (d) After demoting eve, her (freshly re-checked, live-mode) session can no
# longer publish.
def test_demote_eve_blocks_publish():
    admin_token = c.login("root")
    editor_token = c.login("eve")

    # sanity: eve can currently publish a real in-review article (article 3
    # is seeded in_review) before we take her staff role away
    pre = c.publish_article(3, editor_token)
    assert pre.status_code == 200, "expected eve to be able to publish before demotion"

    demote_resp = c.demote("eve", admin_token)
    assert demote_resp.status_code == 200

    fresh_review_id = _make_in_review_article("bob")
    resp = c.publish_article(fresh_review_id, editor_token)
    assert resp.status_code == 403, "demoted eve could still publish"
    assert c.violated_rule(resp) == "inv_publish_staff_only"


# (e) After also deactivating eve, publish is refused too (now on the
# deactivation ground, which is checked ahead of role in the server).
def test_deactivate_eve_blocks_publish():
    admin_token = c.login("root")
    editor_token = c.login("eve")  # eve's role is 'author' by now (see above)

    admin_resp = c.deactivate("eve", admin_token)
    assert admin_resp.status_code == 200

    review_id = _make_in_review_article("bob")
    resp = c.publish_article(review_id, editor_token)
    assert resp.status_code == 403, "deactivated eve could still publish"
    assert c.violated_rule(resp) in ("inv_deactivated_does_nothing", "inv_publish_staff_only")


def _make_in_review_article(author: str) -> int:
    token = c.login(author)
    created = c.create_article(token, title="review-me", body="body")
    article_id = created.json()["id"]
    submit = c.submit_article(article_id, token)
    assert submit.status_code == 200
    return article_id
