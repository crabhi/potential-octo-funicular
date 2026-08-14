"""Flowdeck, running. Boots the generic engine (API + web UI) on the
taskboard rule base and seeds a demo board THROUGH THE RULES over HTTP —
every seed request is decided by rules.yaml, so a seed that violates
policy cannot exist (the janitor's archive below really is refused until
the clock passes the due date).

    python app.py                 # serve on :8800, seed, stay up
    python app.py --port 0        # ephemeral port
    python app.py --seed-only     # seed, print summary, exit (for tests)

Not a line of Flowdeck-specific UI or handler code exists: the board, the
forms, the buttons and the 403 banners are all derived from rules.yaml by
the generic engine (see ../rule-driven-cms/engine/ui.py).
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ENGINE_ROOT = HERE.parent / "rule-driven-cms"
RULESET = HERE / "rulesets" / "taskboard"
sys.path.insert(0, str(ENGINE_ROOT))  # the engine wants to be a package; see DEVLOG

from live_demo import request, wait_ready  # noqa: E402

TODAY = "2026-08-14"

# (creator, fields, [(actor, action), ...]) — replayed over HTTP, under the
# rules. Comments say what each seed demonstrates on the board.
SEED = [
    # team argo — one card per lifecycle column
    ("mira", {"title": "Ship search v2", "estimate": "3d", "assignee": "tom",
              "team": "argo", "due_date": "2026-08-28"},
     [("tom", "start")]),                                    # in progress
    ("pia", {"title": "Fix flaky signup e2e test", "estimate": "1d",
             "assignee": "pia", "team": "argo", "due_date": "2026-08-21"},
     [("pia", "start"), ("pia", "submit")]),                 # in review
    ("mira", {"title": "Rotate API keys", "estimate": "0.5d",
              "assignee": "tom", "team": "argo", "due_date": "2026-09-05"},
     []),                                                    # backlog
    ("tom", {"title": "Onboard new logo designer", "assignee": "pia",
             "team": "argo", "due_date": "2026-09-12"},
     []),                                                    # backlog, no estimate yet
    ("mira", {"title": "Billing dunning emails", "estimate": "2d",
              "assignee": "mira", "team": "argo", "due_date": "2026-09-01"},
     [("mira", "start"), ("mira", "submit"), ("rex", "approve")]),  # done
    ("mira", {"title": "Q2 retro notes", "estimate": "1d", "assignee": "tom",
              "team": "argo", "due_date": "2026-07-31"},
     [("tom", "start"), ("tom", "submit"), ("mira", "approve"),
      ("dusty", "archive")]),                                # archived (past due)
    # team boreal — proves the walls on the same board
    ("kai", {"title": "Migrate Postgres 15 to 16", "estimate": "2d",
             "assignee": "nadia", "team": "boreal", "due_date": "2026-08-25"},
     [("nadia", "start")]),
    ("nadia", {"title": "Renew SOC2 evidence", "estimate": "3d",
               "assignee": "kai", "team": "boreal", "due_date": "2026-09-15"},
     []),
]


def seed(port):
    made = 0
    for creator, fields, moves in SEED:
        status, doc = request(port, "POST", "/tasks", creator, fields)
        assert status == 201, f"seed create by {creator}: HTTP {status} {doc}"
        made += 1
        for actor, action in moves:
            status, doc = request(port, "POST", f"/tasks/{doc['id']}/{action}", actor)
            assert status == 200, \
                f"seed {actor} {action}: HTTP {status} {doc}"
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--db", help="database path (default: a fresh temp file)")
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()

    tmp = None
    db = args.db
    if not db:
        tmp = tempfile.TemporaryDirectory()
        db = f"{tmp.name}/flowdeck.db"

    cmd = [sys.executable, "-m", "engine.server", "--rules", str(RULESET),
           "--db", db, "--port", str(args.port), "--today", TODAY,
           "--mutable-clock", "--ui", "--seed", str(RULESET / "features.yaml")]
    proc = subprocess.Popen(cmd, cwd=ENGINE_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        port = wait_ready(proc)
        n = seed(port)
        print(f"Flowdeck is up: http://127.0.0.1:{port}/ui  "
              f"({n} tasks seeded through the rules; engine date {TODAY})")
        if args.seed_only:
            return 0
        proc.wait()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        if tmp:
            tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
