"""The deliberately reproducible authorization race.

Sequence: eve logs in as editor -> admin demotes (or deactivates) eve ->
eve's *old* token is used to publish an in-review article.

Under AUTH_MODE=cached the session token captured eve's role/active flag
at login time and is trusted verbatim: the stale token still authorizes
publish, reproducing a real check-then-act (TOCTOU) authorization bug —
the same anomaly class as P3's stale-flag-check race, here applied to
authorization state instead of a schema-migration flag.

Under AUTH_MODE=live the same sequence is refused with 403, naming the
invariant it protects (inv_publish_staff_only / inv_deactivated_does_nothing).

Each scenario below starts (and tears down) its *own* fresh server process
so that eve's role/active mutations in one scenario never leak into
another — the in-memory server has no other reset mechanism. This module
is self-contained: it does not require run_demo.sh to have a server
already up on port 3100 (though run_demo.sh does stop its own instances
before invoking this file, to free the port).
"""
import server_control as sc
import cms_client as c


def _setup_and_race(demote_target: bool, deactivate_target: bool):
    """Log eve in as editor, create+submit an in-review article authored
    by bob, then have admin demote and/or deactivate eve. Returns the
    publish response using eve's *original* (pre-mutation) token."""
    admin_token = c.login("root")
    eve_token = c.login("eve")  # captured while eve is still an active editor

    bob_token = c.login("bob")
    created = c.create_article(bob_token, title="race target", body="body")
    article_id = created.json()["id"]
    submit = c.submit_article(article_id, bob_token)
    assert submit.status_code == 200

    if demote_target:
        assert c.demote("eve", admin_token).status_code == 200
    if deactivate_target:
        assert c.deactivate("eve", admin_token).status_code == 200

    return c.publish_article(article_id, eve_token)


def _run_scenario(mode: str, demote_target: bool, deactivate_target: bool):
    proc = sc.start(mode)
    try:
        return _setup_and_race(demote_target, deactivate_target)
    finally:
        sc.stop(proc)


def test_cached_mode_race_via_demote_is_reproducible():
    resp = _run_scenario("cached", demote_target=True, deactivate_target=False)
    assert resp.status_code == 200, (
        "expected the bug: eve's stale cached token should still be "
        "trusted as an editor and successfully publish despite the demote"
    )
    assert resp.json()["state"] == "published"
    print(
        f"[cached] VIOLATION REPRODUCED (demote): stale token published "
        f"article {resp.json()['id']} anyway -- inv_publish_staff_only "
        f"violated in practice"
    )


def test_cached_mode_race_via_deactivate_is_reproducible():
    resp = _run_scenario("cached", demote_target=False, deactivate_target=True)
    assert resp.status_code == 200, (
        "expected the bug: eve's stale cached token should still publish "
        "despite the deactivation"
    )
    assert resp.json()["state"] == "published"
    print(
        f"[cached] VIOLATION REPRODUCED (deactivate): stale token published "
        f"article {resp.json()['id']} anyway -- inv_deactivated_does_nothing "
        f"violated in practice"
    )


def test_live_mode_refuses_same_sequence_via_demote():
    resp = _run_scenario("live", demote_target=True, deactivate_target=False)
    assert resp.status_code == 403
    rule = c.violated_rule(resp)
    assert rule == "inv_publish_staff_only"
    print(f"[live] correctly refused (demote): {rule}")


def test_live_mode_refuses_same_sequence_via_deactivate():
    resp = _run_scenario("live", demote_target=False, deactivate_target=True)
    assert resp.status_code == 403
    rule = c.violated_rule(resp)
    assert rule == "inv_deactivated_does_nothing"
    print(f"[live] correctly refused (deactivate): {rule}")
