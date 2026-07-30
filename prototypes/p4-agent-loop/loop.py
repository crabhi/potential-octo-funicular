#!/usr/bin/env python3
"""P4: closed repair loop.

    checker (Quint) --counterexample--> LLM repairer (headless `claude -p`,
    weaker model) --edit--> checker ... until green or round budget spent.

Governance rules enforced mechanically (research/07 D5, research/08):
- The invariant section of the protocol file is FROZEN. If a repair round
  touches it, the whole round is reverted and counted as failed_spec_edit.
- Every round is logged to episodes/<ep>/round-<k>/ (prompt, agent output,
  resulting file, checker verdict) so the episode is auditable.
"""
import argparse
import datetime
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PROTOCOL = HERE / "protocol" / "migration.qnt"
FROZEN_MARK = "==== INVARIANTS"


def frozen_region(text: str) -> str:
    idx = text.find(FROZEN_MARK)
    if idx < 0:
        sys.exit("frozen marker missing from protocol file")
    return text[idx:]


def typecheck() -> tuple[bool, str]:
    p = subprocess.run(["quint", "typecheck", str(PROTOCOL)],
                       capture_output=True, text=True, timeout=300)
    return p.returncode == 0, p.stdout + p.stderr


def run_feature_gate() -> tuple[bool, str]:
    """Scripted feature/liveness runs (frozen part of the gate)."""
    p = subprocess.run(["quint", "test", str(PROTOCOL), "--main", "migration",
                        "--backend", "typescript"],
                       capture_output=True, text=True, timeout=600)
    return p.returncode == 0, p.stdout + p.stderr


def run_check(itf_path: pathlib.Path, samples: int) -> tuple[bool, str]:
    """Safety simulation + completion-reachability witness."""
    cmd = ["quint", "run", str(PROTOCOL), "--main", "migration",
           "--invariant", "invAll", "--witnesses", "featDone",
           "--backend", "typescript",
           "--max-samples", str(samples), "--max-steps", "30",
           "--out-itf", str(itf_path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    ok = p.returncode == 0
    if ok:  # safety green: also require completion to be reachable at all
        import re
        m = re.search(r"featDone was witnessed in (\d+)", out)
        if not m or int(m.group(1)) == 0:
            ok = False
            out += "\nGATE FAILURE: migration completion (phase == P_DONE) " \
                   "was never reached in any explored trace — the protocol " \
                   "can no longer complete."
    return ok, out


def verify() -> tuple[bool, str]:
    p = subprocess.run(["quint", "verify", str(PROTOCOL), "--main",
                        "migration", "--invariant", "invAll",
                        "--max-steps", "12"],
                       capture_output=True, text=True, timeout=1800)
    return p.returncode == 0, p.stdout + p.stderr


def trim_itf(itf_path: pathlib.Path, max_states: int = 12) -> str:
    try:
        data = json.loads(itf_path.read_text())
    except Exception as e:  # no trace written
        return f"(no ITF trace available: {e})"
    states = data.get("states", [])
    if len(states) > max_states:
        head, tail = states[:2], states[-(max_states - 2):]
        data["states"] = head + [{"#truncated": len(states) - max_states}] + tail
    return json.dumps(data, indent=None, separators=(",", ":"))


PROMPT = """You are an automated repair agent for a formal protocol model.

The file at {path} is a Quint model of an online schema migration: column O
is renamed to N via expand/contract (add N write-only, upgrade app instances
to dual-write, backfill old rows, switch reads to N, drop O), running
concurrently with API requests from two app instances under snapshot
isolation. Rolling upgrades mean v1 instances (which write only O) and v2
instances (which dual-write O and N) coexist for a while.

The repair gate has three frozen parts: safety invariants (reads never
return stale values; O and N agree after the read switch; the switch never
happens before backfill completed), scripted feature runs (required
behaviors that must stay executable end to end), and a completion
reachability check. The checker found the gate red; the failing part and
its output are below.

Your rules:
1. Edit ONLY the action definitions. The section after the line containing
   'INVARIANTS - FROZEN' is frozen: the harness reverts any change there and
   your round fails.
2. Make the minimal protocol change that makes the invariants hold. Reason
   about which real-world migration ordering or criterion is wrong in the
   actions; do not add artificial guards that merely disable functionality
   (e.g. do not make actions unexecutable wholesale).
3. Use the Read tool to read the file and the Edit tool to change it.
   Do not create new files. Do not run shell commands.

Checker summary:
{summary}

Counterexample trace (ITF JSON; vars: phase 0=initial 1=expanded 2=switched,
oState/nState 0=absent 1=writeonly 2=present 3=deleteonly, dbO/dbN maps
key->value with -1 = NULL, logical = value the app believes, bf = in-flight
backfill (active,key,val,snapVer), lastReadOk = ghost):
{itf}
"""


def call_repairer(prompt: str, model: str, log_dir: pathlib.Path) -> str:
    cmd = ["claude", "-p", "--model", model,
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read,Edit"]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       cwd=HERE, timeout=900)
    out = p.stdout + ("\n--- stderr ---\n" + p.stderr if p.stderr else "")
    (log_dir / "claude.log").write_text(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--samples", type=int, default=30000)
    ap.add_argument("--verify", action="store_true",
                    help="run Apalache verification after the loop goes green")
    args = ap.parse_args()

    ep = HERE / "episodes" / datetime.datetime.now().strftime("ep-%Y%m%d-%H%M%S")
    ep.mkdir(parents=True)
    print(f"episode: {ep.relative_to(HERE)}")

    for rnd in range(1, args.rounds + 1):
        rdir = ep / f"round-{rnd}"
        rdir.mkdir()
        itf = rdir / "trace.itf.json"

        ok_tc, tc_out = typecheck()
        if not ok_tc:
            ok, out = False, "TYPECHECK FAILED:\n" + tc_out
        else:
            ok_ft, ft_out = run_feature_gate()
            if not ok_ft:
                ok = False
                out = ("FEATURE GATE FAILED (scripted runs below the FROZEN "
                       "line define required behaviors; read them in the "
                       "file, do not edit them):\n" + ft_out)
            else:
                ok, out = run_check(itf, args.samples)
        (rdir / "check.log").write_text(out)

        if ok:
            print(f"round {rnd}: GREEN (no violation in {args.samples} traces)")
            if args.verify:
                vok, vout = verify()
                (rdir / "verify.log").write_text(vout)
                print(f"  apalache verify: {'NoError' if vok else 'FAILED'}")
                if not vok:
                    continue  # verification found deeper issue; keep looping
            print("loop finished: protocol repaired")
            return
        print(f"round {rnd}: violation found, dispatching repairer ({args.model})")

        before = PROTOCOL.read_text()
        frozen_before = frozen_region(before)
        prompt = PROMPT.format(
            path=PROTOCOL,
            summary=out[-1500:] if ok_tc else out[-3000:],
            itf=trim_itf(itf) if ok_tc else "(typecheck failed; fix the syntax error above first)",
        )
        (rdir / "prompt.txt").write_text(prompt)

        call_repairer(prompt, args.model, rdir)

        after = PROTOCOL.read_text()
        (rdir / "migration.after.qnt").write_text(after)
        if frozen_region(after) != frozen_before:
            PROTOCOL.write_text(before)
            print(f"round {rnd}: SPEC EDIT DETECTED — reverted, round failed")
        elif after == before:
            print(f"round {rnd}: repairer made no edit")

    print("loop finished: round budget exhausted, protocol still red")
    sys.exit(1)


if __name__ == "__main__":
    main()
