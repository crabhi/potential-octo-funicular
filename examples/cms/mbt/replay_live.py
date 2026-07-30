#!/usr/bin/env python3
"""Leg 1: replay every cms_live --mbt trace against the real app running in
AUTH_MODE=live, and score acceptance/state parity. A fresh server process is
started per trace (in-memory state, no reset endpoint -- see app/README.md).

Exit code is 0 iff every step of every trace was accepted (2xx) by the app
AND every observable article-state check matched the model. Non-zero
otherwise -- run_mbt.sh relies on this to fail the whole run on a parity
break in this leg.
"""
import glob
import os
import sys

import adapter

PORT = int(os.environ.get("MBT_PORT", "3300"))
BASE_URL = f"http://127.0.0.1:{PORT}"
TRACE_DIR = os.path.join(os.path.dirname(__file__), "traces", "live")


def main() -> int:
    trace_paths = sorted(glob.glob(os.path.join(TRACE_DIR, "*.itf.json")))
    if not trace_paths:
        print(f"no traces found in {TRACE_DIR}", file=sys.stderr)
        return 2

    total_steps = 0
    total_failures = 0
    total_mismatches = 0
    failing_traces = []

    for path in trace_paths:
        server = adapter.start_server("live", PORT)
        try:
            report = adapter.replay_trace(path, BASE_URL, stop_on_first_reject=False)
        finally:
            adapter.stop_server(server)

        name = os.path.basename(path)
        n_steps = len(report.steps)
        n_fail = sum(1 for s in report.steps if not s.ok)
        total_steps += n_steps
        total_failures += n_fail
        total_mismatches += len(report.state_mismatches)

        status = "PASS" if report.parity_ok else "FAIL"
        print(f"[{status}] {name}: {n_steps} steps, {n_fail} rejected, "
              f"{len(report.state_mismatches)} state mismatches")
        if not report.parity_ok:
            failing_traces.append(name)
            for s in report.steps:
                if not s.ok:
                    print(f"    step {s.index}: {s.action} u={s.u} a={s.a} "
                          f"-> HTTP {s.status_code} {s.detail}  "
                          f"(model transition succeeded -- app should have accepted this)")
            for m in report.state_mismatches:
                print(f"    {m}")

    print()
    print("=== live-vs-cms_live parity scoreboard ===")
    print(f"traces replayed   : {len(trace_paths)}")
    print(f"steps executed    : {total_steps}")
    print(f"rejected steps    : {total_failures}")
    print(f"state mismatches  : {total_mismatches}")
    print(f"failing traces    : {len(failing_traces)} {failing_traces if failing_traces else ''}")

    return 0 if (total_failures == 0 and total_mismatches == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
