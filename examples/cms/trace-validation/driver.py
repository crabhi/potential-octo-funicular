#!/usr/bin/env python3
"""Trace-validation driver: drives a randomized/scripted session against a
*running* CMS server (see ../app/server) over plain HTTP, restricted to the
vocabulary and fixed universe of the Quint model (../model/cms.qnt):

  users:    alice -> model id 1 (author), eve -> model id 2 (editor)
  articles: exactly two, both created by alice during setup, mapped to
            model ids 1 and 2 in creation order (the real server's own
            article ids for these two new drafts are whatever
            next_article_id happens to be -- setup mints them and remembers
            the mapping; they are NOT logged as model actions, matching the
            model's init state where both articles already exist as DRAFT
            authored by alice).

Only these actions are logged as model actions (one JSON line each) when
the server ACCEPTS them (2xx):

  loginU(u)            -- {"action": "loginU", "args": {"u": <1|2>}}
  submitReviewU(u, a)  -- {"action": "submitReviewU", "args": {"u":.., "a":..}}
  publishU(u, a)       -- {"action": "publishU", "args": {"u":.., "a":..}}
  adminDemote          -- {"action": "adminDemote", "args": {"user": <1|2>}}
  adminDeactivate      -- {"action": "adminDeactivate", "args": {"user": <1|2>}}

Rejected attempts (403) are recorded in a separate list in the output and
are NOT included in the accepted-action log used for model replay -- the
model only models successful (committed) actions; a 403 is a no-op on the
model side (state doesn't change), so there is nothing to replay.

Two scenarios are supported (--scenario):

  legal     -- a straight-line editorial workflow that should be legal
               under the model with no admin interference:
               alice logs in, submits article 1 for review; eve logs in,
               publishes article 1.

  stale     -- the cached-session conformance-violation scenario: eve logs
               in (session snapshots her as an active editor), alice logs
               in and submits article 1, an admin demotes eve, then eve's
               *old* token is used to publish article 1 anyway. Against a
               server started with AUTH_MODE=cached this publish is
               ACCEPTED by the app (2xx) -- a real TOCTOU bug -- so it gets
               logged as an accepted publishU, which is exactly the
               sequence the model (CHECK_AT_ACTION=true, i.e. cms_live)
               should refuse when replayed.

Output: a JSON document on stdout (and optionally written to --out) with
  {"accepted": [ {action, args}, ... ], "rejected": [ {action, args, status,
  body}, ... ], "article_map": {"1": <real id>, "2": <real id>}}
"""
import argparse
import json
import sys

import requests


def login(base, user):
    r = requests.post(f"{base}/login", json={"user": user})
    return r


def create_article(base, token, title, body):
    r = requests.post(
        f"{base}/articles",
        json={"title": title, "body": body},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


def submit(base, token, article_id):
    r = requests.post(
        f"{base}/articles/{article_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


def publish(base, token, article_id):
    r = requests.post(
        f"{base}/articles/{article_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


def admin_demote(base, admin_token, target_user):
    r = requests.post(
        f"{base}/admin/demote/{target_user}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return r


def admin_deactivate(base, admin_token, target_user):
    r = requests.post(
        f"{base}/admin/deactivate/{target_user}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return r


# model id <-> real user name (fixed universe, per the model)
USER_MODEL_ID = {"alice": 1, "eve": 2}


class Recorder:
    def __init__(self):
        self.accepted = []
        self.rejected = []

    def record(self, action, args, resp):
        if 200 <= resp.status_code < 300:
            self.accepted.append({"action": action, "args": args})
            print(f"  ACCEPTED {action}({args}) -> {resp.status_code}", file=sys.stderr)
        else:
            body = None
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            self.rejected.append(
                {"action": action, "args": args, "status": resp.status_code, "body": body}
            )
            print(
                f"  REJECTED {action}({args}) -> {resp.status_code} {body}",
                file=sys.stderr,
            )


def setup_articles(base, rec):
    """Create the two model articles as alice (draft, authored by alice --
    matching the model's init state). NOT logged as model actions: article
    creation/pre-seeding is out of the model's action vocabulary; the model
    starts with both articles already existing.

    Returns (alice_token, {1: real_id_1, 2: real_id_2}).
    """
    r = login(base, "alice")
    r.raise_for_status()
    alice_token = r.json()["token"]

    ids = {}
    for model_id, title in ((1, "Model article one"), (2, "Model article two")):
        r = create_article(base, alice_token, title, f"body of {title}")
        r.raise_for_status()
        ids[model_id] = r.json()["id"]
        print(f"  setup: created real article {ids[model_id]} -> model id {model_id}", file=sys.stderr)
    return alice_token, ids


def scenario_legal(base, rec, article_map):
    """alice submits article 1 for review; eve publishes it. No admin
    interference. Should be legal under both cms_live and cms_cached."""
    r = login(base, "alice")
    r.raise_for_status()
    alice_token = r.json()["token"]
    rec.record("loginU", {"u": USER_MODEL_ID["alice"]}, r)

    real_a1 = article_map[1]
    r = submit(base, alice_token, real_a1)
    rec.record("submitReviewU", {"u": USER_MODEL_ID["alice"], "a": 1}, r)

    r = login(base, "eve")
    r.raise_for_status()
    eve_token = r.json()["token"]
    rec.record("loginU", {"u": USER_MODEL_ID["eve"]}, r)

    r = publish(base, eve_token, real_a1)
    rec.record("publishU", {"u": USER_MODEL_ID["eve"], "a": 1}, r)


def scenario_stale(base, rec, article_map):
    """The cached-session TOCTOU scenario: eve logs in first (snapshotting
    her editor role into the token), alice submits article 1 for review, an
    admin demotes eve, then eve's OLD token is used to publish anyway.

    Requires the server to have a 'root' admin account (it does, per
    seed_state in server/src/main.rs) -- admin login/action is driven but
    NOT part of the model's user universe (alice/eve only), so admin's own
    login is not logged as a model action; only the *effect* (adminDemote)
    is logged, matching the model's admin actions which are not
    session-gated.
    """
    r = login(base, "eve")
    r.raise_for_status()
    eve_token = r.json()["token"]
    rec.record("loginU", {"u": USER_MODEL_ID["eve"]}, r)

    r = login(base, "alice")
    r.raise_for_status()
    alice_token = r.json()["token"]
    rec.record("loginU", {"u": USER_MODEL_ID["alice"]}, r)

    real_a1 = article_map[1]
    r = submit(base, alice_token, real_a1)
    rec.record("submitReviewU", {"u": USER_MODEL_ID["alice"], "a": 1}, r)

    r = login(base, "root")
    r.raise_for_status()
    root_token = r.json()["token"]
    # root's login is not part of the model universe -- not logged.

    r = admin_demote(base, root_token, "eve")
    rec.record("adminDemote", {"user": USER_MODEL_ID["eve"]}, r)

    # eve's OLD token -- captured before the demote -- used to publish.
    r = publish(base, eve_token, real_a1)
    rec.record("publishU", {"u": USER_MODEL_ID["eve"], "a": 1}, r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3200")
    ap.add_argument("--scenario", choices=["legal", "stale"], required=True)
    ap.add_argument("--out", default=None, help="write JSON output here too")
    args = ap.parse_args()

    rec = Recorder()
    print(f"driving scenario={args.scenario} against {args.base}", file=sys.stderr)

    alice_token, article_map = setup_articles(args.base, rec)

    if args.scenario == "legal":
        scenario_legal(args.base, rec, article_map)
    else:
        scenario_stale(args.base, rec, article_map)

    out = {
        "scenario": args.scenario,
        "accepted": rec.accepted,
        "rejected": rec.rejected,
        "article_map": {str(k): v for k, v in article_map.items()},
    }
    text = json.dumps(out, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)


if __name__ == "__main__":
    main()
