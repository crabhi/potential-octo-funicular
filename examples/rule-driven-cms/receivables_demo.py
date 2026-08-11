"""End-to-end demo of the receivables service: users register what they
are owed, MockBank emails arrive, the feed bot matches and settles, the
clock bot marks overdue (and is refused when it jumps the calendar), the
notifier mails reminders, a late payment lands, and dashboards stay
tenant-isolated throughout.

    python receivables_demo.py
"""

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from importer import http_json  # noqa: E402
from live_demo import wait_ready  # noqa: E402
from receivables_bots import run_feed, run_notifier, run_sweeper  # noqa: E402

RULESET = "rulesets/receivables"
DAY1, DAY2 = "2026-08-11", "2026-09-10"
failures = 0


def check(ok, label, detail=""):
    global failures
    print(f"   {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    failures += 0 if ok else 1


def register(cms, user, **fields):
    status, doc = http_json("POST", f"{cms}/claims", user, fields)
    assert status == 201, (status, doc)
    return doc["id"]


def main():
    global failures
    with tempfile.TemporaryDirectory() as tmp:
        bank_proc = subprocess.Popen(
            [sys.executable, "mock_bank.py", "--port", "0"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cms_proc = subprocess.Popen(
            [sys.executable, "-m", "engine.server", "--rules", RULESET,
             "--db", f"{tmp}/claims.db", "--port", "0",
             "--seed", f"{RULESET}/features.yaml",
             "--today", DAY1, "--mutable-clock"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            bank = f"http://127.0.0.1:{wait_ready(bank_proc)}"
            cms = f"http://127.0.0.1:{wait_ready(cms_proc)}"
            print(f"== receivables demo: bank {bank} -> cms {cms} (today {DAY1}) ==")

            print("-- users register what they are owed --")
            a = register(cms, "rita", amount="120.00", payer_name="John Smith",
                         due_date="2026-08-20")
            b = register(cms, "rita", amount="89.90", reference="INV-2026-001",
                         due_date="2026-08-25")
            c = register(cms, "rita", amount="500.00", payer_name="Acme s.r.o.",
                         due_date="2026-08-15")
            d = register(cms, "uma", amount="42.00", payer_name="Beta LLC",
                         due_date="2026-09-30")
            check(True, f"4 claims registered (rita: {a},{b},{c}; uma: {d})")
            _, rita_view = http_json("GET", f"{cms}/claims", "rita")
            check({x["id"] for x in rita_view["claims"]} == {a, b, c},
                  "rita's dashboard shows exactly her 3 claims (uma's is invisible)")

            print(f"-- day 1 ({DAY1}): the bank's transaction emails arrive --")
            settled, unmatched = run_feed(cms, bank, "day1")
            check([(cid, via) for _, cid, via in settled]
                  == [(a, "payer name + amount"), (b, "reference")],
                  "matched by approximate name (JOHN SMITH) and exact reference",
                  f"settled {settled}")
            check(unmatched == [("m-003", "no match")],
                  "the stranger's transfer is held for manual review, settles nothing")

            print("-- day 1: the overdue sweeper runs (nothing is due yet) --")
            marked, refused = run_sweeper(cms)
            check(marked == [] and
                  all(why == "no_premature_overdue" for _, why in refused),
                  f"every attempt refused by name: {refused}")

            print(f"-- 30 days pass (clock -> {DAY2}); the sweeper runs again --")
            http_json("POST", f"{cms}/__clock", None, {"today": DAY2})
            marked, refused = run_sweeper(cms)
            check(marked == [c] and refused == [(d, "no_premature_overdue")],
                  f"claim {c} (due 08-15) is overdue; uma's (due 09-30) is protected")

            print("-- the notifier mails reminders for overdue claims --")
            reminders = run_notifier(cms)
            for mail in reminders:
                print(f"        reminder -> {mail['to']}: {mail['subject']}")
            check([m["claim"] for m in reminders] == [c],
                  "exactly one reminder, to the claim's owner")

            print("-- day 2 emails: the late payment finally lands --")
            settled, unmatched = run_feed(cms, bank, "day2")
            check(settled and settled[0][1] == c and not unmatched,
                  f"ACME S.R.O. matches the overdue claim {c}; settle succeeds "
                  f"(late payments land)")

            print("-- the books, per viewer --")
            _, rita_view = http_json("GET", f"{cms}/claims", "rita")
            states = {x["id"]: x["state"] for x in rita_view["claims"]}
            check(states == {a: "paid", b: "paid", c: "paid"},
                  f"rita's dashboard: {states}")
            _, uma_view = http_json("GET", f"{cms}/claims", "uma")
            check([(x["id"], x["state"]) for x in uma_view["claims"]]
                  == [(d, "awaiting")], "uma still awaits Beta LLC — and sees only that")
            _, anon = http_json("GET", f"{cms}/claims")
            check(anon["claims"] == [], "anonymous sees nothing")
            status, ans = http_json("POST", f"{cms}/claims/{d}/settle", "ada")
            check(status == 403 and ans["denied_by"] == "only_feed_settles",
                  "even the admin cannot fake money truth: 403 only_feed_settles")

            print(f"VERDICT: {'PASS' if not failures else f'FAIL ({failures})'}")
            return 1 if failures else 0
        finally:
            for p in (bank_proc, cms_proc):
                p.terminate()
                p.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
