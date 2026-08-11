"""The three background jobs of the receivables service. Each is an
ordinary, unprivileged HTTP client with its own identity — the rule base
decides what it may do, and the analyzer has already checked those rules
over every situation:

  feed (bank_feed)   parses transaction emails, matches them to claims
                     (exact reference, else case-insensitive payer name +
                     exact amount), settles the matched ones. Matching and
                     idempotency are CLIENT logic — cross-item and fuzzy,
                     beyond the per-situation rule vocabulary.
  sweeper (clock)    attempts mark_overdue on every awaiting claim and
                     lets the rules sort it out: premature attempts are
                     refused by name (no_premature_overdue) — the rules
                     hold the clock accountable, not vice versa.
  notifier (mailer)  reads overdue claims and "sends" reminder emails
                     (mock: returns them). Read-only by rule.

    python receivables_bots.py feed   --cms URL --bank URL --day day1
    python receivables_bots.py sweep  --cms URL
    python receivables_bots.py notify --cms URL
"""

import argparse
import re

from importer import http_json


def parse_email(mail):
    """Parse a MockBank notification body into a transaction."""
    get = lambda key: (re.search(rf"^{key}: (.+)$", mail["body"], re.M) or [None, ""])[1]
    reference = get("Reference")
    return {"id": mail["id"], "amount": get("Amount").strip(),
            "payer": get("From").strip(),
            "reference": "" if reference == "(none)" else reference.strip()}


def norm(name):
    return " ".join(name.casefold().split())


def match_claim(tx, claims):
    """Exact reference first; else approximate payer name + exact amount."""
    open_claims = [c for c in claims if c["state"] in ("awaiting", "overdue")]
    if tx["reference"]:
        by_ref = [c for c in open_claims if c["reference"] == tx["reference"]]
        if by_ref:
            return by_ref[0] if len(by_ref) == 1 else "ambiguous"
    by_name = [c for c in open_claims
               if c["payer_name"] and norm(c["payer_name"]) == norm(tx["payer"])
               and c["amount"] == tx["amount"]]
    if by_name:
        return by_name[0] if len(by_name) == 1 else "ambiguous"
    return None


def run_feed(cms, bank, day, user="feedbot"):
    """Returns (settled [(email id, claim id, via)], unmatched [email ids])."""
    _, doc = http_json("GET", f"{cms}/claims", user)
    claims = doc["claims"]
    _, inbox = http_json("GET", f"{bank}/inbox/{day}")
    settled, unmatched = [], []
    for mail in inbox["emails"]:
        tx = parse_email(mail)
        claim = match_claim(tx, claims)
        if claim is None or claim == "ambiguous":
            unmatched.append((tx["id"], claim or "no match"))
            continue
        status, ans = http_json("POST", f"{cms}/claims/{claim['id']}/settle", user)
        if status != 200:
            raise RuntimeError(f"settle claim {claim['id']}: HTTP {status} {ans}")
        claim["state"] = "paid"  # keep the local view current for later emails
        via = "reference" if tx["reference"] and claim["reference"] == tx["reference"] \
            else "payer name + amount"
        settled.append((tx["id"], claim["id"], via))
    return settled, unmatched


def run_sweeper(cms, user="tick"):
    """Returns (marked claim ids, refused [(claim id, denied_by)])."""
    _, doc = http_json("GET", f"{cms}/claims", user)
    marked, refused = [], []
    for claim in doc["claims"]:
        if claim["state"] != "awaiting":
            continue
        status, ans = http_json("POST", f"{cms}/claims/{claim['id']}/mark_overdue", user)
        if status == 200:
            marked.append(claim["id"])
        else:
            refused.append((claim["id"], ans.get("denied_by", f"HTTP {status}")))
    return marked, refused


def run_notifier(cms, user="mailer"):
    """Returns the reminder 'emails' for overdue claims."""
    _, doc = http_json("GET", f"{cms}/claims", user)
    return [{"to": f"{c['author']}@example.com",
             "subject": f"Payment overdue: EUR {c['amount']} "
                        f"(due {c['due_date']})",
             "claim": c["id"]}
            for c in doc["claims"] if c["state"] == "overdue"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["feed", "sweep", "notify"])
    ap.add_argument("--cms", required=True)
    ap.add_argument("--bank")
    ap.add_argument("--day", default="day1")
    args = ap.parse_args()
    if args.job == "feed":
        settled, unmatched = run_feed(args.cms, args.bank, args.day)
        for eid, cid, via in settled:
            print(f"  {eid}: settled claim {cid} (matched by {via})")
        for eid, why in unmatched:
            print(f"  {eid}: UNMATCHED ({why}) — held for manual review")
    elif args.job == "sweep":
        marked, refused = run_sweeper(args.cms)
        print(f"  marked overdue: {marked}; refused: {refused}")
    else:
        for mail in run_notifier(args.cms):
            print(f"  reminder -> {mail['to']}: {mail['subject']}")


if __name__ == "__main__":
    main()
