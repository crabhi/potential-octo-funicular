"""Mock bank — the source of transaction notification emails.

Serves the inbox of parsed-but-raw notification emails the bank sends
after each incoming transfer, in daily batches:

    GET /inbox/day1  -> {"emails": [{id, subject, body}, ...]}
    GET /inbox/day2  -> ...

    python mock_bank.py --port 0   # prints READY port=<n>
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def email(eid, amount, payer, reference=""):
    return {
        "id": eid,
        "subject": f"Credit received: EUR {amount}",
        "body": (f"Amount: {amount}\n"
                 f"From: {payer}\n"
                 f"Reference: {reference or '(none)'}\n"
                 f"This is an automated notification from MockBank."),
    }


INBOX = {
    "day1": [
        email("m-001", "120.00", "JOHN SMITH"),
        email("m-002", "89.90", "PAYMENTS GMBH", "INV-2026-001"),
        email("m-003", "33.33", "UNKNOWN STRANGER"),
    ],
    "day2": [
        email("m-004", "500.00", "ACME S.R.O."),
    ],
}

ROUTE = re.compile(r"^/inbox/(day\d+)$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        m = ROUTE.match(self.path)
        payload = {"emails": INBOX[m.group(1)]} if m and m.group(1) in INBOX \
            else None
        body = json.dumps(payload if payload else {"error": "no_such_batch"}).encode()
        self.send_response(200 if payload else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"READY port={httpd.server_address[1]} batches={len(INBOX)}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
