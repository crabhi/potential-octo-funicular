"""The deliberately reproducible authorization race.

Sequence: eve logs in as editor -> admin demotes (or deactivates) eve ->
eve's *old* token is used to publish an in-review article.

Under AUTH_MODE=cached the session token captured eve's role/active flag
at login time and is trusted verbatim: the stale token still authorizes
publish, reproducing a real check-then-act (TOCTOU) authorization bug —
exactly the class of anomaly P3's stale-flag-check race demonstrates for
schema migrations, here applied to authorization state instead.

Under AUTH_MODE=live the same sequence is refused with 403, naming the
invariant it protects (inv_publish_staff_only / inv_deactivated_does_nothing).

This module expects CMS_MODE env var to tell it which server it's talking
to (set by run_demo.sh), so it can pick the correct expected outcome and
assertion. Running it against the wrong mode's server would give a
misleading pass/fail, so we fail loudly if CMS_MODE is unset.
"""
import os

import pytest

import cms_client as c

MODE = os.environ.get("CMS_MODE")
if MODE not in ("cached", "live"):
    pytest.skip(
        "CMS_MODE env var must be 'cached' or 'live' to run this module "
        "(set by run_demo.sh)",
        allow_module_level=True,
    )


def _setup_race():
    """Log eve in as editor, create+submit an in-review article authored
    by bob, then have admin demote eve out of her editor role. Returns
    (eve_token, article_id)."""
    admin_token = c.login("root")
    eve_token = c.login("eve")  # captured while eve is still an active editor

    bob_token = c.login("bob")
    created = c.create_article(bob_token, title="race target", body="body")
    article_id = created.json()["id"]
    submit = c.submit_article(article_id, bob_token)
    assert submit.status_code == 200

    demote_resp = c.demote("eve", admin_token)
    assert demote_resp.status_code == 200

    return eve_token, article_id


def test_stale_session_race_via_demote():
    eve_token, article_id = _setup_race()
    resp = c.publish_article(article_id, eve_token)

    if MODE == "cached":
        assert resp.status_code == 200, (
            "expected the bug: eve's stale cached token should still be "
            "trusted as an editor and successfully publish, in cached mode"
        )
        assert resp.json()["state"] == "published"
        print(
            f"[cached] VIOLATION REPRODUCED: demoted eve's stale token "
            f"published article {article_id} anyway (inv_publish_staff_only "
            f"violated in practice)"
        )
    else:
        assert resp.status_code == 403, "live mode should re-check eve's role and refuse"
        rule = c.violated_rule(resp)
        assert rule == "inv_publish_staff_only"
        print(f"[live] correctly refused: {rule}")


def test_stale_session_race_via_deactivate():
    admin_token = c.login("root")
    eve_token = c.login("eve")

    bob_token = c.login("bob")
    created = c.create_article(bob_token, title="race target 2", body="body")
    article_id = created.json()["id"]
    submit = c.submit_article(article_id, bob_token)
    assert submit.status_code == 200

    deact_resp = c.deactivate("eve", admin_token)
    assert deact_resp.status_code == 200

    resp = c.publish_article(article_id, eve_token)

    if MODE == "cached":
        assert resp.status_code == 200, (
            "expected the bug: deactivated eve's stale token should still "
            "publish successfully in cached mode"
        )
        print(
            f"[cached] VIOLATION REPRODUCED: deactivated eve's stale token "
            f"published article {article_id} anyway "
            f"(inv_deactivated_does_nothing violated in practice)"
        )
    else:
        assert resp.status_code == 403
        rule = c.violated_rule(resp)
        assert rule == "inv_deactivated_does_nothing"
        print(f"[live] correctly refused: {rule}")
