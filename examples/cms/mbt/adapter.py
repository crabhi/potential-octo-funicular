"""Model-based test adapter: replay a Quint --mbt ITF trace against the real
CMS HTTP API and assert parity between what the model permitted and what the
app actually did.

Concept (Track C, see ../../../research/09-bridging-the-gap.md):
  the MODEL generates a test sequence (quint run --mbt --out-itf ...);
  this adapter REPLAYS it against the REAL app over HTTP;
  a comparator asserts ACCEPTANCE PARITY: the app accepts exactly the
  actions the model's transition succeeded on, and the resulting
  observable state (article states) matches the model's.

Model <-> app correspondence
-----------------------------
Model users: USERS = {1, 2}, ALICE = 1 (author), EVE = 2 (editor).
App users:   alice (author), eve (editor) are seeded with exactly those
             roles, so no user setup is needed -- the mapping is the
             identity map {1: "alice", 2: "eve"}.

Model articles: ARTICLES = {1, 2}, both authored by ALICE, both DRAFT in
`init`. The app's seed data does NOT match this (4 articles, mixed authors
and states -- see app/server/src/main.rs seed_state) -- so this adapter
runs a SETUP phase before replay: log in as alice and create two fresh
draft articles. Their freshly assigned app article ids become the mapping
targets for model article ids 1 and 2. This makes the app's post-setup
state exactly the model's `init` state, which the brief calls out as the
condition for the two to be comparable at all.

Model article states: DRAFT=0, IN_REVIEW=1, PUBLISHED=2 map to the app's
"draft" / "in_review" / "published" strings.

Admin actions (adminDemote/adminDeactivate) are not modeled with an acting
admin user -- role.get(u) is just mutated. The app requires an admin
bearer token for those endpoints, so the adapter logs in as "root" (app's
seeded admin) once during setup; this login is bookkeeping, not a replayed
model step.

Action -> HTTP mapping
-----------------------
  init            -> (setup only, not replayed as a step)
  login           -> POST /login                      as mapped user
  adminDemote     -> POST /admin/demote/{user}         as root (admin)
  adminDeactivate -> POST /admin/deactivate/{user}      as root (admin)
  submitReview    -> POST /articles/{id}/submit         as mapped user
  publish         -> POST /articles/{id}/publish        as mapped user

The u/a arguments are read directly from `mbt::nondetPicks` in the ITF
trace -- the --mbt flag hands us the exact nondet choice the simulator
made, which is why this adapter does not need to diff consecutive states
to recover action arguments (diffing was the fallback the brief
suggested; nondetPicks made it unnecessary here -- see README "what was
painful").
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import time
from typing import Optional

import requests

USER_MAP = {1: "alice", 2: "eve"}
ARTSTATE_MAP = {0: "draft", 1: "in_review", 2: "published"}

SERVER_MANIFEST = os.path.join(
    os.path.dirname(__file__), "..", "app", "server", "Cargo.toml"
)


# --------------------------------------------------------------------------
# ITF decoding -- minimal decoder for the subset of the format cms.qnt uses:
# #bigint, #map, #tup, and the {tag: Some|None, value: ...} option encoding
# that --mbt emits for nondetPicks.
# --------------------------------------------------------------------------

def itf_val(v):
    if isinstance(v, dict):
        if "#bigint" in v:
            return int(v["#bigint"])
        if "#map" in v:
            return {itf_val(k): itf_val(val) for k, val in v["#map"]}
        if "#tup" in v:
            return tuple(itf_val(x) for x in v["#tup"])
        if "tag" in v:  # Option type from nondetPicks
            if v["tag"] == "Some":
                return itf_val(v["value"])
            return None
        # Generic Quint record (e.g. mbt::nondetPicks itself: {a: Option, u:
        # Option}) -- recurse into each field.
        return {k: itf_val(val) for k, val in v.items()}
    return v  # bool / str / int already plain


def load_trace(path: str) -> list[dict]:
    with open(path) as f:
        doc = json.load(f)
    states = []
    for s in doc["states"]:
        decoded = {k: itf_val(v) for k, v in s.items() if k != "#meta"}
        decoded["_index"] = s.get("#meta", {}).get("index")
        states.append(decoded)
    return states


def var_key(states: list[dict], suffix: str) -> str:
    """The model's vars are namespaced e.g. 'cms_live::cms::artState' or
    'cms_cached::cms::artState' depending on --main. Find the actual key."""
    for k in states[0]:
        if k.endswith("::" + suffix):
            return k
    raise KeyError(f"no var ending in ::{suffix} in trace")


# --------------------------------------------------------------------------
# Server lifecycle
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Server:
    proc: subprocess.Popen
    base_url: str


def start_server(mode: str, port: int, timeout: float = 20.0) -> Server:
    env = dict(os.environ)
    env["AUTH_MODE"] = mode
    env["CMS_ADDR"] = f"0.0.0.0:{port}"
    proc = subprocess.Popen(
        ["cargo", "run", "--quiet", "--manifest-path", SERVER_MANIFEST],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{base_url}/health", timeout=0.5).status_code == 200:
                return Server(proc, base_url)
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"cms-server ({mode}) exited early with code {proc.returncode}")
        time.sleep(0.15)
    stop_server(Server(proc, base_url))
    raise TimeoutError(f"cms-server ({mode}) did not become healthy in {timeout}s")


def stop_server(server: Server) -> None:
    if server.proc.poll() is None:
        server.proc.terminate()
        try:
            server.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.proc.kill()
            server.proc.wait(timeout=5)
    _wait_port_closed(server.base_url, timeout=5.0)


def _wait_port_closed(base_url: str, timeout: float = 5.0) -> None:
    """Block until the port is no longer accepting connections, so the next
    start_server() on the same port doesn't race the OS releasing it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{base_url}/health", timeout=0.3)
            time.sleep(0.1)
        except requests.RequestException:
            return
    # Give up waiting; the caller's next bind will surface any real problem.


# --------------------------------------------------------------------------
# Setup: bring the app to the model's `init` state
# --------------------------------------------------------------------------

@dataclasses.dataclass
class ReplayCtx:
    base_url: str
    tokens: dict[int, str] = dataclasses.field(default_factory=dict)  # model user -> token
    admin_token: str = ""
    art_map: dict[int, int] = dataclasses.field(default_factory=dict)  # model art id -> app art id


def http_login(base_url: str, user: str) -> requests.Response:
    return requests.post(f"{base_url}/login", json={"user": user}, timeout=5)


def setup(base_url: str) -> ReplayCtx:
    ctx = ReplayCtx(base_url=base_url)

    # Admin bookkeeping token (not a replayed model step -- the model has
    # no acting user for adminDemote/adminDeactivate).
    r = http_login(base_url, "root")
    r.raise_for_status()
    ctx.admin_token = r.json()["token"]

    # Log in as alice once to create the two draft articles the model's
    # `init` assumes. This IS setup, distinct from any later `login` step
    # replayed from the trace (the trace will log alice in again -- the
    # app supports multiple concurrent sessions per user, matching the
    # model's single-session-per-user abstraction closely enough that a
    # second alice token is simply unused after the first submitReview).
    r = http_login(base_url, "alice")
    r.raise_for_status()
    setup_token = r.json()["token"]

    for model_art_id in (1, 2):
        r = requests.post(
            f"{base_url}/articles",
            json={"title": f"mbt seed article {model_art_id}", "body": "mbt setup"},
            headers={"Authorization": f"Bearer {setup_token}"},
            timeout=5,
        )
        r.raise_for_status()
        app_id = r.json()["id"]
        ctx.art_map[model_art_id] = app_id

    return ctx


# --------------------------------------------------------------------------
# Step replay
# --------------------------------------------------------------------------

@dataclasses.dataclass
class StepResult:
    index: int
    action: str
    u: Optional[int]
    a: Optional[int]
    http_method: str
    http_path: str
    status_code: int
    ok: bool          # HTTP call succeeded (2xx)
    model_ok: bool     # the model's transition succeeded (always True for
                        # states appearing in an ITF trace -- see README)
    detail: str = ""


def do_step(ctx: ReplayCtx, action: str, u: Optional[int], a: Optional[int]) -> StepResult:
    base = ctx.base_url

    if action == "login":
        user = USER_MAP[u]
        r = http_login(base, user)
        if r.status_code // 100 == 2:
            ctx.tokens[u] = r.json()["token"]
        return StepResult(-1, action, u, a, "POST", "/login", r.status_code, r.status_code // 100 == 2, True)

    if action == "adminDemote":
        user = USER_MAP[u]
        r = requests.post(
            f"{base}/admin/demote/{user}",
            headers={"Authorization": f"Bearer {ctx.admin_token}"},
            timeout=5,
        )
        return StepResult(-1, action, u, a, "POST", f"/admin/demote/{user}", r.status_code, r.status_code // 100 == 2, True)

    if action == "adminDeactivate":
        user = USER_MAP[u]
        r = requests.post(
            f"{base}/admin/deactivate/{user}",
            headers={"Authorization": f"Bearer {ctx.admin_token}"},
            timeout=5,
        )
        return StepResult(-1, action, u, a, "POST", f"/admin/deactivate/{user}", r.status_code, r.status_code // 100 == 2, True)

    if action == "submitReview":
        app_art_id = ctx.art_map[a]
        token = ctx.tokens.get(u, "")
        r = requests.post(
            f"{base}/articles/{app_art_id}/submit",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        detail = "" if r.status_code // 100 == 2 else _err(r)
        return StepResult(-1, action, u, a, "POST", f"/articles/{app_art_id}/submit", r.status_code, r.status_code // 100 == 2, True, detail)

    if action == "publish":
        app_art_id = ctx.art_map[a]
        token = ctx.tokens.get(u, "")
        r = requests.post(
            f"{base}/articles/{app_art_id}/publish",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        detail = "" if r.status_code // 100 == 2 else _err(r)
        return StepResult(-1, action, u, a, "POST", f"/articles/{app_art_id}/publish", r.status_code, r.status_code // 100 == 2, True, detail)

    raise ValueError(f"unhandled action {action!r}")


def _err(r: requests.Response) -> str:
    try:
        return r.json().get("error", r.text)
    except ValueError:
        return r.text


def get_article_state(ctx: ReplayCtx, model_art_id: int) -> str:
    """Fetch observable article state using the admin token (admin can see
    every state) so this check is independent of whichever user's session
    the trace happens to have logged in at this point."""
    app_id = ctx.art_map[model_art_id]
    r = requests.get(
        f"{ctx.base_url}/articles/{app_id}",
        headers={"Authorization": f"Bearer {ctx.admin_token}"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["state"]


# --------------------------------------------------------------------------
# Full-trace replay
# --------------------------------------------------------------------------

@dataclasses.dataclass
class TraceReport:
    trace_path: str
    steps: list[StepResult]
    state_mismatches: list[str]
    stopped_early_at: Optional[int] = None

    @property
    def parity_ok(self) -> bool:
        return all(s.ok for s in self.steps) and not self.state_mismatches


def replay_trace(trace_path: str, base_url: str, stop_on_first_reject: bool = False) -> TraceReport:
    states = load_trace(trace_path)
    art_state_key = var_key(states, "artState")

    ctx = setup(base_url)
    steps: list[StepResult] = []
    mismatches: list[str] = []
    stopped_at = None

    for i in range(1, len(states)):
        st = states[i]
        action = st["mbt::actionTaken"]
        picks = st["mbt::nondetPicks"]
        u = picks.get("u")
        a = picks.get("a")

        result = do_step(ctx, action, u, a)
        result.index = i
        steps.append(result)

        if not result.ok:
            if stop_on_first_reject:
                stopped_at = i
                break
            continue

        # Observable-state parity check: for article-affecting actions,
        # the app's article state must match the model's artState at
        # this point in the trace.
        if action in ("submitReview", "publish"):
            model_state_int = st[art_state_key][a]
            expected = ARTSTATE_MAP[model_state_int]
            actual = get_article_state(ctx, a)
            if actual != expected:
                mismatches.append(
                    f"step {i} ({action} u={u} a={a}): model says article "
                    f"{a} is {expected!r}, app says {actual!r}"
                )

    return TraceReport(trace_path, steps, mismatches, stopped_at)
