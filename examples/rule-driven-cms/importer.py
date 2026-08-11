"""Nightly import job (SYND-9): fetch published articles from the
publisher feeds and deliver them INTO REVIEW at the CMS.

The job is deliberately unprivileged plumbing — a plain HTTP client with
the `imp-bot` identity. Everything interesting about it is decided by the
rule base, not by this code: it cannot skip provenance
(`import_needs_provenance`), cannot touch content or decide anything
(`importer_scope`, `no_self_decision`), and editors still publish. A
compromised importer is contained by rules the analyzer has already
checked over every situation.

Idempotency (dedup by `source` = "<publisher>#<id>") lives here, client-
side: "no two articles with the same source" is a cross-item invariant the
per-situation rule vocabulary cannot state — see README, "the projection
boundary".

    python importer.py --cms http://127.0.0.1:8080 --feeds http://127.0.0.1:9090
    # nightly:  0 3 * * *  python importer.py --cms ... --feeds ...
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

USER = "imp-bot"


def http_json(method, url, user=None, body=None):
    req = urllib.request.Request(url, method=method)
    if user and user != "anonymous":
        req.add_header("X-User", user)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def run_import(cms, feeds, user=USER):
    """Returns (imported source keys, skipped count). Safe to re-run."""
    status, doc = http_json("GET", f"{cms}/articles", user)
    assert status == 200, doc
    seen = {a["source"] for a in doc["articles"] if a.get("source")}

    imported, skipped = [], 0
    _, pubs = http_json("GET", f"{feeds}/publishers")
    for slug in pubs["publishers"]:
        _, feed = http_json("GET", f"{feeds}/publishers/{slug}/articles")
        for art in feed["articles"]:
            key = f"{slug}#{art['id']}"
            if key in seen:
                skipped += 1
                continue
            status, created = http_json("POST", f"{cms}/articles", user, {
                "title": art["title"], "body": art["body"], "source": key})
            if status != 201:
                raise RuntimeError(f"create {key}: HTTP {status} {created}")
            status, doc = http_json(
                "POST", f"{cms}/articles/{created['id']}/submit", user)
            if status != 200:
                raise RuntimeError(f"submit {key}: HTTP {status} {doc}")
            imported.append(key)
    return imported, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cms", required=True)
    ap.add_argument("--feeds", required=True)
    ap.add_argument("--user", default=USER)
    args = ap.parse_args()
    imported, skipped = run_import(args.cms, args.feeds, args.user)
    for key in imported:
        print(f"  imported {key} -> in_review")
    print(f"import run done: {len(imported)} imported, {skipped} already present")


if __name__ == "__main__":
    main()
