#!/usr/bin/env bash
# End-to-end Track C runner: model-based test generation.
#
#   1. quint run --mbt generates trace files (the model drives, in --out-itf
#      / ITF JSON form).
#   2. replay_live.py replays every cms_live trace against the real app
#      (AUTH_MODE=live) and scores acceptance/state parity.
#   3. divergence_demo.py replays cms_cached "race" traces against the real
#      app (AUTH_MODE=live) to demonstrate the conformance signal (see that
#      file's docstring for which direction and why).
#
# Exits non-zero if the live-vs-cms_live parity leg (step 2) fails. The
# divergence demo (step 3) is a demonstration, not a gate on the main
# parity claim, but a "silent vulnerability" result there also fails the
# run (see divergence_demo.py).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

MODEL="../model/cms.qnt"
export MBT_PORT="${MBT_PORT:-3300}"

N_LIVE_TRACES="${N_LIVE_TRACES:-20}"
N_CACHED_RACE_TRACES="${N_CACHED_RACE_TRACES:-6}"
MAX_STEPS="${MAX_STEPS:-12}"

VENV="../app/harness/.venv"
if [ -x "$VENV/bin/python3" ]; then
  PY="$VENV/bin/python3"
else
  echo "== no ../app/harness/.venv found, creating mbt/.venv =="
  python3 -m venv .venv
  PY=".venv/bin/python3"
  "$PY" -m pip install --quiet requests
fi
echo "using python: $PY"

CLEANUP_PIDS=()
cleanup() {
  for pid in "${CLEANUP_PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  # Also sweep anything still bound to our port (e.g. a killed-but-lingering
  # cargo child) -- best-effort, never fatal.
  pkill -f "cms-server" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== building cms-server (cargo build) =="
( cd ../app/server && cargo build --quiet ) || { echo "server build failed"; exit 1; }

echo
echo "== step 1: generating traces with quint run --mbt =="
rm -rf traces/live traces/cached
mkdir -p traces/live traces/cached

echo "-- ${N_LIVE_TRACES} cms_live traces (max-steps=${MAX_STEPS}) --"
quint run "$MODEL" --main cms_live --mbt \
  --out-itf "traces/live/trace.itf.json" \
  --n-traces "$N_LIVE_TRACES" --max-steps "$MAX_STEPS" --backend typescript \
  > traces/live/gen.log 2>&1
if ! ls traces/live/trace*.itf.json >/dev/null 2>&1; then
  echo "trace generation failed -- see traces/live/gen.log"; tail -40 traces/live/gen.log
  exit 1
fi
tail -3 traces/live/gen.log
echo "  wrote $(ls traces/live/*.itf.json | wc -l) live trace files"

echo
echo "-- ${N_CACHED_RACE_TRACES} cms_cached race traces (--invariant invNoUnauthorizedActions) --"
# quint run halts each invocation at the first invariant violation, so each
# call produces exactly one counterexample trace; loop to get several.
n_ok=0
for i in $(seq 1 "$N_CACHED_RACE_TRACES"); do
  out="traces/cached/race_${i}.itf.json"
  if quint run "$MODEL" --main cms_cached --mbt --invariant invNoUnauthorizedActions \
       --out-itf "$out" --n-traces 1 --max-steps "$MAX_STEPS" --backend typescript \
       > "traces/cached/gen_${i}.log" 2>&1; then
    :
  fi
  if [ -f "$out" ]; then
    n_ok=$((n_ok + 1))
  fi
done
echo "  wrote ${n_ok}/${N_CACHED_RACE_TRACES} cached race trace files"
if [ "$n_ok" -eq 0 ]; then
  echo "no cached race traces generated -- see traces/cached/gen_*.log"
  exit 1
fi

echo
echo "== step 2: replaying cms_live traces against the LIVE app (parity leg) =="
"$PY" replay_live.py
LIVE_STATUS=$?

echo
echo "== step 3: divergence demo (cms_cached race traces -> LIVE app) =="
"$PY" divergence_demo.py
DIVERGENCE_STATUS=$?

echo
echo "================================================================"
echo "TRACK C (mbt) RUN SUMMARY"
echo "  live-vs-cms_live parity leg : $([ $LIVE_STATUS -eq 0 ] && echo PASS || echo FAIL)"
echo "  divergence demo             : $([ $DIVERGENCE_STATUS -eq 0 ] && echo 'CONFIRMED (as expected)' || echo 'UNEXPECTED RESULT')"
echo "================================================================"

# The brief requires non-zero exit specifically on a parity failure in the
# live-vs-cms_live leg.
exit "$LIVE_STATUS"
