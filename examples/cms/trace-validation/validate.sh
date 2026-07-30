#!/usr/bin/env bash
# End-to-end trace-validation demo (Track B, research/09-bridging-the-gap.md).
#
# 1. Start the real CMS server (../app/server) in AUTH_MODE=live on port
#    3200, drive a legal editorial-workflow session against it, compile the
#    accepted-action log into a generated Quint run, `quint test` it ->
#    expect PASS ("legal behavior").
# 2. Start the same server in AUTH_MODE=cached (default) on port 3200,
#    drive the stale-session sequence (login eve, demote eve via admin,
#    reuse eve's OLD token to publish -- the app ACCEPTS this in cached
#    mode), compile, `quint test` it -> expect FAIL: the canonical
#    (CHECK_AT_ACTION=true) model refuses the publish step even though the
#    real app let it through -> CONFORMANCE VIOLATION DETECTED.
#
# Kills every server it starts, including on error (trap).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HERE/../app"
SERVER_BIN="$APP_DIR/server/target/debug/cms-server"
PORT=3200
BASE_URL="http://127.0.0.1:${PORT}"

VENV_PY="$APP_DIR/harness/.venv/bin/python3"
if [ ! -x "$VENV_PY" ]; then
  echo "harness venv not found at $VENV_PY; creating a local venv instead" >&2
  python3 -m venv "$HERE/.venv"
  "$HERE/.venv/bin/pip" install -q requests
  VENV_PY="$HERE/.venv/bin/python3"
fi

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  # Also sweep anything still bound to our port (belt and suspenders).
  fuser -k "${PORT}/tcp" 2>/dev/null || true
}
trap cleanup EXIT

start_server() {
  local mode="$1"
  AUTH_MODE="$mode" CMS_ADDR="0.0.0.0:${PORT}" "$SERVER_BIN" >"$HERE/server-${mode}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 50); do
    if curl -s -o /dev/null "$BASE_URL/health"; then
      return 0
    fi
    sleep 0.1
  done
  echo "server (mode=$mode) did not come up" >&2
  cat "$HERE/server-${mode}.log" >&2
  return 1
}

stop_server() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  SERVER_PID=""
}

if [ ! -x "$SERVER_BIN" ]; then
  echo "building server binary..." >&2
  ( cd "$APP_DIR/server" && cargo build --quiet ) || { echo "cargo build failed" >&2; exit 1; }
fi

OVERALL_OK=true

echo "=========================================================="
echo "SCENARIO 1: legal editorial workflow, AUTH_MODE=live, port ${PORT}"
echo "=========================================================="
start_server live || exit 1
"$VENV_PY" "$HERE/driver.py" --base "$BASE_URL" --scenario legal --out "$HERE/log-legal.json" >/dev/null
DRIVER_LEGAL_RC=$?
stop_server
if [ "$DRIVER_LEGAL_RC" -ne 0 ]; then
  echo "driver (legal scenario) failed" >&2
  OVERALL_OK=false
fi

python3 "$HERE/log2run.py" "$HERE/log-legal.json" --out "$HERE/generated_trace_legal.qnt" \
  --check-at-action true --module-name generated_trace_legal --run-name traceReplayTest

echo "--- generated_trace_legal.qnt ---"
cat "$HERE/generated_trace_legal.qnt"
echo "--- quint test (expect PASS) ---"
( cd "$HERE" && quint test generated_trace_legal.qnt --main generated_trace_legal --backend typescript --match traceReplayTest ) \
  | tee "$HERE/quint-legal.out"
LEGAL_QUINT_RC=${PIPESTATUS[0]:-$?}
if [ "$LEGAL_QUINT_RC" -eq 0 ]; then
  echo ">>> PASS: legal trace confirmed legal by the model."
else
  echo ">>> UNEXPECTED: legal trace was rejected by the model!" >&2
  OVERALL_OK=false
fi

echo
echo "=========================================================="
echo "SCENARIO 2: stale-session race, AUTH_MODE=cached, port ${PORT}"
echo "=========================================================="
start_server cached || exit 1
"$VENV_PY" "$HERE/driver.py" --base "$BASE_URL" --scenario stale --out "$HERE/log-stale.json" >/dev/null
DRIVER_STALE_RC=$?
stop_server
if [ "$DRIVER_STALE_RC" -ne 0 ]; then
  echo "driver (stale scenario) failed" >&2
  OVERALL_OK=false
fi

python3 "$HERE/log2run.py" "$HERE/log-stale.json" --out "$HERE/generated_trace_stale.qnt" \
  --check-at-action true --module-name generated_trace_stale --run-name traceReplayTest

echo "--- generated_trace_stale.qnt ---"
cat "$HERE/generated_trace_stale.qnt"
echo "--- quint test (expect FAIL = conformance violation caught) ---"
( cd "$HERE" && quint test generated_trace_stale.qnt --main generated_trace_stale --backend typescript --match traceReplayTest ) \
  | tee "$HERE/quint-stale.out"
STALE_QUINT_RC=${PIPESTATUS[0]:-$?}
if [ "$STALE_QUINT_RC" -ne 0 ]; then
  echo ">>> CONFORMANCE VIOLATION DETECTED: the app accepted the stale-session publish (2xx) but the canonical model refuses that publish step."
else
  echo ">>> UNEXPECTED: stale-session trace was accepted by the model too!" >&2
  OVERALL_OK=false
fi

echo
echo "=========================================================="
echo "SUMMARY"
echo "=========================================================="
echo "legal scenario:  driver_rc=$DRIVER_LEGAL_RC quint_rc=$LEGAL_QUINT_RC (expect quint_rc=0)"
echo "stale scenario:  driver_rc=$DRIVER_STALE_RC quint_rc=$STALE_QUINT_RC (expect quint_rc!=0)"

if [ "$OVERALL_OK" = "true" ] && [ "$LEGAL_QUINT_RC" -eq 0 ] && [ "$STALE_QUINT_RC" -ne 0 ]; then
  echo "RESULT: both outcomes demonstrated as expected."
  exit 0
else
  echo "RESULT: unexpected outcome(s), see above." >&2
  exit 1
fi
