"""The JSON API — an adapter over the kernel. Generic: it serves whatever
rule base it is given, and it contains no enforcement of its own: every
decision happens inside engine.kernel (guardrail 10), this module only
maps kernel outcomes onto HTTP.

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

A refusal is HTTP 403 whose body names the denying rule — the same
vocabulary the analyzer, the gate files and the rule base use.
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import features as features_mod
from .kernel import Denied, Illegal, Kernel, evaluate  # noqa: F401 (evaluate re-exported)


def make_handler(rb, conn, clock=None, mutable_clock=False):
    kernel = Kernel(rb, conn, clock if clock is not None else {})
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
            return kernel.actor(self.headers.get("X-User"))

        def item_json(self, row):
            doc = {"id": row["id"], "author": row["author"], "state": row["state"]}
            for f in rb.fields:
                doc[f] = row[f]
            return doc

        def refuse(self, e):
            """Map a kernel refusal onto the wire, rule named."""
            if isinstance(e, Illegal):
                return self.send_json(400, {
                    "error": "invalid_transition",
                    "detail": f"cannot {e.action} in state {e.state!r}"})
            self.send_json(403, {"error": "forbidden", "denied_by": e.rule.id,
                                 "description": e.rule.description,
                                 "situation": e.situation})

        # -- verbs -------------------------------------------------------------
        def do_GET(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            if self.path == f"/{plural}":
                visible = [self.item_json(r) for r in kernel.visible(actor)]
                return self.send_json(200, {plural: visible})
            m = route_one.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            try:
                row = kernel.get(actor, m.group(1))
            except Denied as e:
                return self.refuse(e)
            if row is None:
                return self.send_json(404, {"error": "not_found"})
            self.send_json(200, self.item_json(row))

        def do_POST(self):
            if self.path == "/__clock":
                # test seam, enabled only by --mutable-clock: lets demos and
                # feature replays advance the engine's date deterministically
                if not mutable_clock:
                    return self.send_json(404, {"error": "no_such_route"})
                body = self.read_body()
                if not body or "today" not in body:
                    return self.send_json(400, {"error": "bad_json"})
                kernel.set_today(body["today"])
                return self.send_json(200, {"today": kernel.today})
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            if self.path == f"/{plural}":
                body = self.read_body()
                if body is None:
                    return self.send_json(400, {"error": "bad_json"})
                try:
                    row = kernel.create(actor, {f: str(body.get(f, ""))
                                                for f in rb.fields})
                except (Denied, Illegal) as e:
                    return self.refuse(e)
                return self.send_json(201, self.item_json(row))
            m = route_action.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            item_id, action = m.group(1), m.group(2)
            if action not in rb.actions or rb.transition_for(action) is None:
                return self.send_json(404, {"error": "unknown_action", "action": action})
            try:
                row = kernel.act(actor, action, item_id)
            except KeyError:
                return self.send_json(404, {"error": "not_found"})
            except (Denied, Illegal) as e:
                return self.refuse(e)
            self.send_json(200, self.item_json(row))

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
            try:
                row = kernel.edit(actor, m.group(1), body)
            except KeyError:
                return self.send_json(404, {"error": "not_found"})
            except (Denied, Illegal) as e:
                return self.refuse(e)
            self.send_json(200, self.item_json(row))

        def do_DELETE(self):
            actor = self.actor()
            if actor is None:
                return self.send_json(401, {"error": "unknown_user"})
            m = route_one.match(self.path)
            if not m:
                return self.send_json(404, {"error": "no_such_route"})
            try:
                kernel.delete(actor, m.group(1))
            except KeyError:
                return self.send_json(404, {"error": "not_found"})
            except (Denied, Illegal) as e:
                return self.refuse(e)
            self.send_json(200, {"deleted": int(m.group(1))})

    Handler.kernel = kernel  # subclassing adapters (the generic UI) share it
    return Handler


def main():
    import datetime

    from . import rulebase as rb_mod
    from . import store

    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True, help="ruleset directory (with rules.yaml)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--seed", help="features.yaml whose actors become users")
    ap.add_argument("--today", default=datetime.date.today().isoformat(),
                    help="the engine's current date (ISO), feeding date projections")
    ap.add_argument("--mutable-clock", action="store_true",
                    help="test seam: enable POST /__clock to change the date")
    ap.add_argument("--ui", action="store_true",
                    help="also serve the generic web UI under /ui")
    args = ap.parse_args()

    rb = rb_mod.load(f"{args.rules}/rules.yaml")
    seed_actors = features_mod.load(args.seed)[0] if args.seed else None
    conn = store.open_db(args.db, rb, seed_actors)
    factory = make_handler
    if args.ui:
        from . import ui
        factory = ui.make_handler
    handler = factory(rb, conn, clock={"today": args.today},
                      mutable_clock=args.mutable_clock)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"READY port={httpd.server_address[1]} entity={rb.entity} "
          f"today={args.today}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
