"""End-to-end demo of the nightly import: mock publisher feeds + the CMS
served from the rule base + the importer job — then the editorial workflow
finishing what the pipeline started, and the containment rules refusing
what it must never do.

    python import_demo.py
"""

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from importer import http_json, run_import  # noqa: E402
from live_demo import wait_ready  # noqa: E402

RULESET = "rulesets/cms"
failures = 0


def check(ok, label, detail=""):
    global failures
    print(f"   {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    failures += 0 if ok else 1


def main():
    with tempfile.TemporaryDirectory() as tmp:
        feeds_proc = subprocess.Popen(
            [sys.executable, "mock_publishers.py", "--port", "0"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cms_proc = subprocess.Popen(
            [sys.executable, "-m", "engine.server", "--rules", RULESET,
             "--db", f"{tmp}/import.db", "--port", "0",
             "--seed", f"{RULESET}/features.yaml"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            feeds = f"http://127.0.0.1:{wait_ready(feeds_proc)}"
            cms = f"http://127.0.0.1:{wait_ready(cms_proc)}"
            print(f"== nightly import demo: feeds {feeds} -> cms {cms} ==")

            print("-- night 1: the import job runs --")
            imported, skipped = run_import(cms, feeds)
            check(len(imported) == 7 and skipped == 0,
                  f"imported {len(imported)} articles from 3 publishers "
                  f"({skipped} skipped)")
            _, doc = http_json("GET", f"{cms}/articles", "imp-bot")
            states = {a["state"] for a in doc["articles"]}
            sourced = all(a["source"] for a in doc["articles"])
            check(states == {"in_review"} and sourced,
                  "every import is in_review and carries its provenance")

            print("-- night 2: nothing new at the publishers --")
            imported2, skipped2 = run_import(cms, feeds)
            check(imported2 == [] and skipped2 == 7,
                  f"idempotent: {len(imported2)} imported, {skipped2} skipped")

            print("-- the rules contain the pipeline (over live HTTP) --")
            first = doc["articles"][0]["id"]
            status, ans = http_json("POST", f"{cms}/articles/{first}/publish", "imp-bot")
            check(status == 403 and ans.get("denied_by") == "no_self_decision",
                  f"imp-bot may not publish its own import: 403 {ans.get('denied_by')}")
            status, ans = http_json("PUT", f"{cms}/articles/{first}", "imp-bot",
                                    {"body": "tampered"})
            check(status == 403 and ans.get("denied_by") == "importer_scope",
                  f"imp-bot may not edit content: 403 {ans.get('denied_by')}")
            status, ans = http_json("POST", f"{cms}/articles", "imp-bot",
                                    {"title": "no origin", "body": "x"})
            check(status == 403 and ans.get("denied_by") == "import_needs_provenance",
                  f"sourceless import refused: 403 {ans.get('denied_by')}")

            print("-- morning: an editor decides, the public reads --")
            status, ans = http_json("POST", f"{cms}/articles/{first}/publish", "ed")
            check(status == 200 and ans["state"] == "published",
                  f"editor publishes article {first} ({ans.get('source', '?')})")
            _, anon = http_json("GET", f"{cms}/articles")
            visible = [(a["id"], a["state"]) for a in anon["articles"]]
            check(visible == [(first, "published")],
                  f"anonymous sees exactly the published import: {visible}")

            print(f"VERDICT: {'PASS' if not failures else f'FAIL ({failures})'}")
            return 1 if failures else 0
        finally:
            for p in (feeds_proc, cms_proc):
                p.terminate()
                p.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
