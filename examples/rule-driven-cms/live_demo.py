"""Live demo: boot the generic server on a ruleset and replay the SAME
frozen feature file over real HTTP. Outcomes must match the pure engine —
including WHICH rule denied (the 403 body names it). Then a visibility
probe: the list endpoint as anonymous vs editor, compared against what the
decision function predicts.

    python live_demo.py rulesets/cms [--port 0]
"""

import argparse
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import features as features_mod  # noqa: E402
from engine import rulebase as rb_mod  # noqa: E402


def request(port, method, path, user=None, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
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


class HttpExecutor:
    """Mirrors engine.features.PureExecutor, but over the wire."""

    def __init__(self, rb, port):
        self.rb = rb
        self.port = port
        self.plural = rb.entity + "s"
        self.item_id = None

    def step(self, step):
        rb, actor, action = self.rb, step["actor"], step["action"]
        payload = step.get("set") or {}
        t = rb.transition_for(action)
        if t is not None and t.source == rb_mod.NO_STATE:
            status, doc = request(self.port, "POST", f"/{self.plural}", actor, payload)
        elif action == "read":
            status, doc = request(self.port, "GET", f"/{self.plural}/{self.item_id}", actor)
        elif action == "edit":
            status, doc = request(self.port, "PUT", f"/{self.plural}/{self.item_id}",
                                  actor, payload)
        elif action == "delete":
            status, doc = request(self.port, "DELETE", f"/{self.plural}/{self.item_id}", actor)
        else:
            status, doc = request(self.port, "POST",
                                  f"/{self.plural}/{self.item_id}/{action}", actor)

        if step["expect"] == "allow":
            if status not in (200, 201):
                return False, f"expected success, got HTTP {status}: {doc}"
            if "id" in doc:
                self.item_id = doc["id"]
            want = step.get("state_after")
            if want and doc.get("state") != want:
                return False, f"state is {doc.get('state')}, expected {want}"
            return True, ""
        if status != 403:
            return False, f"expected 403, got HTTP {status}: {doc}"
        want = step.get("denied_by")
        if want and doc.get("denied_by") != want:
            return False, f"denied by {doc.get('denied_by')}, expected {want}"
        return True, ""


def wait_ready(proc, timeout=15):
    line = proc.stdout.readline().decode()
    if not line.startswith("READY"):
        raise RuntimeError(f"server did not start: {line!r}")
    deadline = time.time() + timeout
    port = int(line.split("port=")[1].split()[0])
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return port
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server never accepted connections")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruleset")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()

    rb = rb_mod.load(f"{args.ruleset}/rules.yaml")
    features_path = f"{args.ruleset}/features.yaml"
    actors, features = features_mod.load(features_path)

    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.Popen(
            [sys.executable, "-m", "engine.server", "--rules", args.ruleset,
             "--db", f"{tmp}/live.db", "--port", str(args.port),
             "--seed", features_path],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            port = wait_ready(proc)
            print(f"== live demo: {rb.entity} service from {args.ruleset} "
                  f"on port {port} ==")
            failures = 0

            print("-- frozen feature runs, replayed over real HTTP --")
            for feature in features:
                ex = HttpExecutor(rb, port)
                ok, msg = True, ""
                for i, step in enumerate(feature["steps"], 1):
                    ok, msg = ex.step(step)
                    if not ok:
                        msg = f"step {i} ({step['actor']} {step['action']}): {msg}"
                        break
                print(f"   {'ok  ' if ok else 'FAIL'} {feature['id']}"
                      + (f" — {msg}" if msg else f" ({len(feature['steps'])} steps)"))
                failures += 0 if ok else 1

            print("-- visibility probe: list endpoint vs decision function --")
            plural = rb.entity + "s"
            _, all_items = request(port, "GET", f"/{plural}",
                                   next(n for n, a in actors.items() if a.role == "admin"))
            for viewer in ["anonymous"] + [n for n, a in actors.items()
                                           if a.role in ("editor", "agent")][:1]:
                actor = actors[viewer]
                predicted = set()
                for item in all_items[plural]:
                    s = rb.situation(actor.role, actor.active,
                                     item["author"] == viewer, "read", item["state"],
                                     {f: item[f] for f in rb.fields})
                    if rb.decide(s).effect == "allow":
                        predicted.add(item["id"])
                _, visible = request(port, "GET", f"/{plural}", viewer)
                got = {i["id"] for i in visible[plural]}
                states = sorted(i["state"] for i in visible[plural])
                if got == predicted:
                    print(f"   ok   as {viewer}: sees {len(got)}/{len(all_items[plural])} "
                          f"items {states} — exactly as the rules predict")
                else:
                    print(f"   FAIL as {viewer}: sees {sorted(got)}, rules predict "
                          f"{sorted(predicted)}")
                    failures += 1

            print(f"VERDICT: {'PASS' if not failures else f'FAIL ({failures})'}")
            return 1 if failures else 0
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
