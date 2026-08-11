"""The web service. Generic: it serves whatever rule base it is given.

    python -m engine.server --rules rulesets/cms --db /tmp/cms.db --port 8080 \
        [--seed rulesets/cms/features.yaml]

Routes (entity name taken from the rule base; `article` shown):

    POST   /articles              create (the lifecycle's from-`none` transition)
    GET    /articles              list — each item filtered by the read rule
    GET    /articles/<id>         read
    PUT    /articles/<id>         edit (body: field values)
    DELETE /articles/<id>         delete
    POST   /articles/<id>/<t>     any other lifecycle transition (submit, ...)

Identity is the X-User header (seeded users; absent = anonymous) — this
example is about authorization rules, not authentication.

Every request goes: structural lifecycle check -> rule decision -> action.
A refusal is HTTP 403 whose body names the denying rule — the same
vocabulary the analyzer, the gate files, and the rule base use.
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import features as features_mod
from . import rulebase as rb_mod
from . import store


def make_handler(rb, conn):
    plural = rb.entity + "s"
    route_one = re.compile(rf"^/{plural}/(\d+)$")
    route_action = re.compile(rf"^/{plural}/(\d+)/([a-z_]+)$")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        # -- plumbing ---------------------------------------------------------
        def send_json(self, code, payload):
            body = json.dumps(payload, indent=1).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                doc = json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                return None
            return doc if isinstance(doc, dict) else None

        def actor(self):
            name = self.headers.get("X-User")
            if not name:
                return features_mod.ANONYMOUS
            row = store.get_user(conn, name)
            if row is None:
                return None
            return features_mod.Actor(row["name"], row["role"], bool(row["active"]))

        def item_json(self, row):
            doc = {"id": row["id"], "author": row["author"], "state": row["state"]}
            for f in rb.fields:
                doc[f] = row[f]
            return doc

        # -- the one enforcement point ----------------------------------------
        def authorize(self, actor, action, row, new_fields=None):
            """Returns None if allowed, else sends the refusal response."""
            state = row["state"] if row is not None else rb_mod.NO_STATE
            if not rb.lifecycle_legal(action, state):
                self.send_json(400, {"error": "invalid_transition",
                                     "detail": f"cannot {action} in state {state!r}"})
                return "sent"
            fields = new_fields if row is None else {f: row[f] for f in rb.fields}
            is_author = True if row is None else actor.name == row["author"]
            situation = rb.situation(actor.role, actor.active, is_author,
                                     action, state, fields)
            verdict = rb.decide(situation)
            if verdict.effect == "deny":
                self.send_json(403, {"error": "forbidden", "denied_by": verdict.id,
                                     "description": verdict.description,
                                     "situation": situation})
                return "sent"
            return None

        def with_item(self, item_id):
            row = store.get_item(conn, int(item_id))
            if row is None:
                self.send_json(404, {"error": "not_found"})
            return row

        # -- verbs -------------------------------------------------------------
        def do_GET(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            if self.path == f"/{plural}":
                visible = [self.item_json(r) for r in store.list_items(conn)
                           if self.authorize_quiet(actor, "read", r)]
                return self.send_json(200, {plural: visible})
            m = route_one.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            row = self.with_item(m.group(1))
            if row is None:
                return
            if self.authorize(actor, "read", row) is None:
                self.send_json(200, self.item_json(row))

        def authorize_quiet(self, actor, action, row):
            situation = rb.situation(actor.role, actor.active,
                                     actor.name == row["author"], action,
                                     row["state"], {f: row[f] for f in rb.fields})
            return rb.decide(situation).effect == "allow"

        def do_POST(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            if self.path == f"/{plural}":
                body = self.read_body()
                if body is None:
                    return self.send_json(400, {"error": "bad_json"})
                t = rb.creating_transition()
                fields = {f: str(body.get(f, "")) for f in rb.fields}
                if self.authorize(actor, t.action, None, new_fields=fields) is None:
                    item_id = store.create_item(conn, rb, actor.name, t.target, fields)
                    self.send_json(201, self.item_json(store.get_item(conn, item_id)))
                return
            m = route_action.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            item_id, action = m.group(1), m.group(2)
            if action not in rb.actions or rb.transition_for(action) is None:
                return self.send_json(404, {"error": "unknown_action", "action": action})
            row = self.with_item(item_id)
            if row is None:
                return
            if self.authorize(actor, action, row) is None:
                store.update_item(conn, rb, row["id"],
                                  {"state": rb.transition_for(action).target})
                self.send_json(200, self.item_json(store.get_item(conn, row["id"])))

        def do_PUT(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            m = route_one.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            body = self.read_body()
            if body is None:
                return self.send_json(400, {"error": "bad_json"})
            row = self.with_item(m.group(1))
            if row is None:
                return
            if self.authorize(actor, "edit", row) is None:
                store.update_item(conn, rb, row["id"],
                                  {f: str(v) for f, v in body.items() if f in rb.fields})
                self.send_json(200, self.item_json(store.get_item(conn, row["id"])))

        def do_DELETE(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            m = route_one.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            row = self.with_item(m.group(1))
            if row is None:
                return
            if self.authorize(actor, "delete", row) is None:
                store.delete_item(conn, row["id"])
                self.send_json(200, {"deleted": row["id"]})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True, help="ruleset directory (with rules.yaml)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--seed", help="features.yaml whose actors become users")
    args = ap.parse_args()

    rb = rb_mod.load(f"{args.rules}/rules.yaml")
    seed_actors = features_mod.load(args.seed)[0] if args.seed else None
    conn = store.open_db(args.db, rb, seed_actors)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(rb, conn))
    print(f"READY port={httpd.server_address[1]} entity={rb.entity}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
