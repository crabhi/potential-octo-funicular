#!/usr/bin/env bash
# Demo CMS: builds the Rust/axum server, runs the Python/Hypothesis policy
# suite against it in AUTH_MODE=live (expect all green), then runs the
# self-managed stale-session race suite, which demonstrates the same
# sequence being a real violation under AUTH_MODE=cached and correctly
# refused under AUTH_MODE=live. Idempotent; kills anything it started.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$HERE/server"
HARNESS_DIR="$HERE/harness"
BIN="$SERVER_DIR/target/debug/cms-server"
PORT=3100
BASE_URL="http://127.0.0.1:${PORT}"

SERVER_PID=""

cleanup() {
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
    # belt-and-suspenders: anything else bound to our port from a previous
    # interrupted run of this script.
    pkill -f "$BIN" 2>/dev/null || true
}
trap cleanup EXIT

wait_healthy() {
    for _ in $(seq 1 50); do
        if curl -s -o /dev/null -w '' "$BASE_URL/health" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    return 1
}

echo "== killing any stray cms-server from a previous run =="
pkill -f "$BIN" 2>/dev/null || true
sleep 0.3

echo "== building server =="
(cd "$SERVER_DIR" && cargo build --quiet) || { echo "build failed"; exit 1; }

echo "== provisioning harness venv =="
if [[ ! -d "$HARNESS_DIR/.venv" ]]; then
    python3 -m venv "$HARNESS_DIR/.venv"
fi
"$HARNESS_DIR/.venv/bin/pip" install --quiet -r "$HARNESS_DIR/requirements.txt"

echo
echo "== starting server in AUTH_MODE=live =="
AUTH_MODE=live CMS_ADDR="0.0.0.0:${PORT}" "$BIN" >/tmp/cms-server-live.log 2>&1 &
SERVER_PID=$!
if ! wait_healthy; then
    echo "server did not become healthy"
    cat /tmp/cms-server-live.log
    exit 1
fi

echo "== running policy suite (live mode; expect all green) =="
(
    cd "$HARNESS_DIR" && \
    CMS_BASE_URL="$BASE_URL" .venv/bin/python3 -m pytest test_policy.py -v
)
POLICY_STATUS=$?
POLICY_PASS=$( [[ $POLICY_STATUS -eq 0 ]] && echo 5 || echo 0 )

echo
echo "== stopping live-mode server (race suite manages its own instances) =="
kill "$SERVER_PID" 2>/dev/null
wait "$SERVER_PID" 2>/dev/null
SERVER_PID=""
sleep 0.3

echo "== running stale-session race suite (self-managed cached + live instances) =="
(
    cd "$HARNESS_DIR" && \
    CMS_SERVER_BIN="$BIN" CMS_PORT="$PORT" \
    .venv/bin/python3 -m pytest test_stale_session_race.py -v -s
)
RACE_STATUS=$?

VIOLATIONS_REPRODUCED=0
REFUSALS_IN_LIVE=0
if [[ $RACE_STATUS -eq 0 ]]; then
    VIOLATIONS_REPRODUCED=2   # demote + deactivate, both reproduced in cached mode
    REFUSALS_IN_LIVE=2        # demote + deactivate, both refused with 403 in live mode
fi

echo
echo "================= SUMMARY ================="
echo "policy checks passed (live mode):      ${POLICY_PASS}/5"
echo "violations reproduced (cached mode):    ${VIOLATIONS_REPRODUCED}/2"
echo "refusals confirmed (live mode, race):   ${REFUSALS_IN_LIVE}/2"
echo "============================================="

if [[ $POLICY_STATUS -ne 0 || $RACE_STATUS -ne 0 ]]; then
    echo "DEMO FAILED"
    exit 1
fi
echo "DEMO OK"
