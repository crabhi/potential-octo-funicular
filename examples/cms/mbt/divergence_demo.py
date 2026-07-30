#!/usr/bin/env python3
"""Leg 2: the conformance-divergence demo.

Direction implemented, and why
-------------------------------
There are two possible directions to check here:

  (a) replay a cms_live trace onto the app running in AUTH_MODE=cached.
      A cms_live trace never contains an action the live policy forbids
      (lastActionOk stays true throughout, by construction of the model),
      so this direction predicts NO divergence: the cached app should
      accept every step too, since cached mode is only ever MORE
      permissive than live mode, never less. Running this direction would
      just reconfirm "cached accepts a subset-or-equal of what live
      accepts" -- true but uninteresting, and it cannot exercise the
      actual bug class (cached wrongly ALLOWING something).

  (b) replay a cms_cached trace onto the app running in AUTH_MODE=live.
      cms_cached's guards use the SESSION's cached role/active snapshot
      (effRole/effActive), so a cms_cached trace can legally reach a step
      where the model transitions successfully (submitReview/publish
      commits) while its ghost variable lastActionOk flips to false --
      meaning the cached model just permitted an action the live security
      policy forbids (classic stale-session TOCTOU: login while active
      editor, get demoted/deactivated, act anyway). Replaying that exact
      step onto the LIVE app is the meaningful check: does the real
      server's live re-authorization actually catch what the
      cached-semantics model let through? If the live app also accepts
      it, that's a real vulnerability. If it rejects it, that 403 is the
      conformance signal this track is built to produce.

This script implements (b). For each cms_cached "race" trace (generated
with `--invariant invNoUnauthorizedActions`, so each trace ends exactly at
the first cached-model-allowed-but-live-policy-forbidden step):
  - replay every step up to (not including) the divergence point against a
    LIVE-mode app, asserting normal acceptance (these are legitimate
    actions unaffected by the cached/live distinction: logins, admin
    demote/deactivate, and any earlier submits/publishes);
  - at the step where the model's lastActionOk flips true -> false, assert
    that the LIVE app's HTTP call is REJECTED (403). That mismatch --
    "model-with-cached-semantics said yes, app-with-live-semantics said
    no" -- is printed loudly as the conformance signal.
"""
import glob
import os
import sys

import adapter

PORT = int(os.environ.get("MBT_PORT", "3300"))
BASE_URL = f"http://127.0.0.1:{PORT}"
TRACE_DIR = os.path.join(os.path.dirname(__file__), "traces", "cached")


def run_one(path: str) -> dict:
    states = adapter.load_trace(path)
    ok_key = adapter.var_key(states, "lastActionOk")

    server = adapter.start_server("live", PORT)
    try:
        ctx = adapter.setup(BASE_URL)
        divergence_index = None
        divergence_step = None
        unexpected_failure = None

        for i in range(1, len(states)):
            st = states[i]
            action = st["mbt::actionTaken"]
            picks = st["mbt::nondetPicks"]
            u, a = picks.get("u"), picks.get("a")

            prev_ok = states[i - 1][ok_key]
            cur_ok = st[ok_key]
            is_divergence_point = prev_ok and not cur_ok

            result = adapter.do_step(ctx, action, u, a)
            result.index = i

            if is_divergence_point:
                divergence_index = i
                divergence_step = result
                break  # app state now diverges from the model; stop here
            elif not result.ok:
                unexpected_failure = result
                break
    finally:
        adapter.stop_server(server)

    return {
        "path": path,
        "divergence_index": divergence_index,
        "divergence_step": divergence_step,
        "unexpected_failure": unexpected_failure,
    }


def main() -> int:
    trace_paths = sorted(glob.glob(os.path.join(TRACE_DIR, "*.itf.json")))
    if not trace_paths:
        print(f"no cached-model race traces found in {TRACE_DIR}", file=sys.stderr)
        return 2

    print("=== Divergence demo: cms_cached trace replayed onto the LIVE app ===")
    print("(direction (b) -- see module docstring for why)")
    print()

    confirmed = 0
    silent_vuln = 0
    no_opportunity = 0
    broken = 0

    for path in trace_paths:
        name = os.path.basename(path)
        r = run_one(path)

        if r["unexpected_failure"] is not None:
            s = r["unexpected_failure"]
            print(f"[BROKEN]     {name}: step {s.index} ({s.action} u={s.u} a={s.a}) "
                  f"unexpectedly rejected (HTTP {s.status_code} {s.detail}) before "
                  f"reaching the divergence point -- not the signal we're looking for")
            broken += 1
            continue

        if r["divergence_index"] is None:
            print(f"[NO-OP]      {name}: no cached-model-allowed/live-forbidden step "
                  f"found in this trace (lastActionOk stayed true throughout)")
            no_opportunity += 1
            continue

        s = r["divergence_step"]
        if s.ok:
            print(f"[VULNERABLE] {name}: step {s.index} ({s.action} u={s.u} a={s.a}) "
                  f"-- cms_cached model allowed this (lastActionOk: true->false) "
                  f"and the LIVE APP ALSO ACCEPTED IT (HTTP {s.status_code}). "
                  f"This would be a real stale-session vulnerability.")
            silent_vuln += 1
        else:
            print(f"[CONFIRMED]  {name}: step {s.index} ({s.action} u={s.u} a={s.a}) "
                  f"-- cms_cached model allowed this (lastActionOk: true->false) "
                  f"but the LIVE APP REJECTED IT (HTTP {s.status_code} {s.detail}). "
                  f"Live re-authorization catches exactly what the cached-semantics "
                  f"model missed.")
            confirmed += 1

    print()
    print("=== divergence demo scoreboard ===")
    print(f"race traces replayed        : {len(trace_paths)}")
    print(f"divergence confirmed (403)  : {confirmed}")
    print(f"silent vulnerability (200)  : {silent_vuln}")
    print(f"no divergence opportunity   : {no_opportunity}")
    print(f"broken before divergence    : {broken}")

    # This demo's job is to show the signal, not to gate the run -- a
    # silent_vuln finding IS the finding (would indicate the live server
    # itself regressed), so surface it via exit code too.
    return 0 if (silent_vuln == 0 and broken == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
