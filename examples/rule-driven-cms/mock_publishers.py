"""Mock publisher feeds — the external side of the nightly import.

A deliberately tiny syndication API (three publishers, canned articles):

    GET /publishers                      -> {"publishers": [slug, ...]}
    GET /publishers/<slug>/articles      -> {"articles": [{id, title, body}]}

    python mock_publishers.py --port 0   # prints READY port=<n>
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FEEDS = {
    "daily-bugle": [
        {"id": 101, "title": "Vigilante spotted downtown",
         "body": "Eyewitnesses report web-shaped residue on 5th Avenue."},
        {"id": 102, "title": "City budget passes",
         "body": "The council approved the budget 7-2 after a long night."},
        {"id": 103, "title": "Bridge repairs ahead of schedule",
         "body": "Engineers credit dry weather and a new alloy."},
    ],
    "planet-news": [
        {"id": 7, "title": "Meteor shower peaks Friday",
         "body": "Best viewing after midnight, away from city lights."},
        {"id": 8, "title": "Museum reopens east wing",
         "body": "The renovated wing features interactive exhibits."},
    ],
    "the-gazette": [
        {"id": 55, "title": "Local bakery wins national prize",
         "body": "The sourdough category was reportedly fierce."},
        {"id": 56, "title": "Rail line adds night service",
         "body": "Hourly trains until 2am starting next month."},
    ],
}

ROUTE = re.compile(r"^/publishers/([a-z-]+)/articles$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/publishers":
            return self.send_json(200, {"publishers": sorted(FEEDS)})
        m = ROUTE.match(self.path)
        if m and m.group(1) in FEEDS:
            return self.send_json(200, {"articles": FEEDS[m.group(1)]})
        self.send_json(404, {"error": "no_such_feed"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"READY port={httpd.server_address[1]} publishers={len(FEEDS)}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
