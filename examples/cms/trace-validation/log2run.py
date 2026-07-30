#!/usr/bin/env python3
"""Compile a driver.py accepted-action log (JSON, {"accepted": [...]}) into
a generated Quint module that replays exactly that sequence of actions as a
single `run`, against the real ../model/cms module, and asks: "was this a
legal behavior?" via `.expect(lastActionOk)`.

Vocabulary handled (matches the model's parameterized/bare actions):
  loginU(u)            -> .then(loginU(<u>))
  submitReviewU(u, a)  -> .then(submitReviewU(<u>, <a>))
  publishU(u, a)       -> .then(publishU(<u>, <a>))
  adminDemote          -> .then(adminDemote)       -- bare nondet action;
  adminDeactivate      -> .then(adminDeactivate)   -- see NOTE below.

NOTE on admin actions: the model (../model/cms.qnt) only exposes
adminDemote/adminDeactivate as *nondet* actions (`nondet u = USERS.oneOf()`)
with no parameterized adminDemoteU(u)/adminDeactivateU(u) counterpart, so
the generated run cannot pin down *which* user the model applies the action
to -- it relies on the model's own guard to make the nondet choice
effectively deterministic (e.g. adminDemote's guard `role.get(u) == EDITOR`
is only satisfiable by whichever single user is currently an editor in our
restricted 2-user universe). This is verified empirically to behave
deterministically for the scenarios this prototype drives (single eligible
user), but it is NOT sound in general: if the model's user universe ever
had two simultaneously-eligible targets, `.then(adminDemote)` could not
express "demote *this* one" and the compiled run would be ambiguous/flaky.
See NEEDS_MODEL_CHANGE.md for the (non-blocking) suggested model addition
that would remove this caveat.
"""
import argparse
import json
import sys


def qnt_action_for(entry):
    action = entry["action"]
    args = entry.get("args", {})
    if action == "loginU":
        return f"loginU({args['u']})"
    if action == "submitReviewU":
        return f"submitReviewU({args['u']}, {args['a']})"
    if action == "publishU":
        return f"publishU({args['u']}, {args['a']})"
    if action == "adminDemote":
        # bare nondet action -- see module docstring NOTE.
        return "adminDemote"
    if action == "adminDeactivate":
        return "adminDeactivate"
    raise ValueError(f"unrecognized action in log: {action!r}")


def compile_run(accepted, check_at_action, module_name="generated_trace", run_name="traceReplayTest"):
    lines = []
    lines.append(f"module {module_name} {{")
    ca = "true" if check_at_action else "false"
    lines.append(f"  import cms(CHECK_AT_ACTION = {ca}).* from \"../model/cms\"")
    lines.append("")
    lines.append(f"  run {run_name} = init")
    for entry in accepted:
        comment = ""
        if entry["action"] in ("adminDemote", "adminDeactivate"):
            comment = f"  // target (from log, informational only): {entry.get('args')}"
        lines.append(f"    .then({qnt_action_for(entry)}){comment}")
    lines.append("    .expect(lastActionOk)")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="path to driver.py JSON output (has an 'accepted' key)")
    ap.add_argument("--out", required=True, help="output .qnt file path")
    ap.add_argument(
        "--check-at-action",
        choices=["true", "false"],
        required=True,
        help="true -> cms_live (checked at moment of action), false -> cms_cached (stale snapshot trusted)",
    )
    ap.add_argument("--module-name", default="generated_trace")
    ap.add_argument("--run-name", default="traceReplayTest")
    args = ap.parse_args()

    with open(args.log) as f:
        data = json.load(f)
    accepted = data["accepted"]
    if not accepted:
        print("warning: no accepted actions in log; generated run will be just init.expect(lastActionOk)", file=sys.stderr)

    text = compile_run(
        accepted,
        check_at_action=(args.check_at_action == "true"),
        module_name=args.module_name,
        run_name=args.run_name,
    )
    with open(args.out, "w") as f:
        f.write(text)
    print(f"wrote {args.out} ({len(accepted)} actions compiled, module={args.module_name}, CHECK_AT_ACTION={args.check_at_action})", file=sys.stderr)


if __name__ == "__main__":
    main()
