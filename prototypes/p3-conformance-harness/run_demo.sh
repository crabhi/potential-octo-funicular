#!/usr/bin/env bash
# P3 conformance harness: end-to-end demo.
#
# Builds the Rust API, ensures Postgres is up, resets the schema, starts two
# API instances (v1 on 3001, v2 on 3002), runs the Python/Hypothesis test
# harness against them while the real migration executes concurrently, and
# prints results. Idempotent: safe to re-run; it kills any instances it
# previously started and resets the DB schema each time.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$HERE/api"
MIGRATE_DIR="$HERE/migrate"
HARNESS_DIR="$HERE/harness"
PIDFILE="$HERE/.demo_pids"

export DATABASE_URL="${DATABASE_URL:-host=127.0.0.1 port=5432 dbname=p3demo user=root password=p3demo}"

log() { echo "[run_demo] $*"; }

cleanup_previous() {
    if [[ -f "$PIDFILE" ]]; then
        log "stopping previously started instances ($(cat "$PIDFILE" | tr '\n' ' '))"
        while read -r pid; do
            kill "$pid" 2>/dev/null || true
        done < "$PIDFILE"
        rm -f "$PIDFILE"
        sleep 0.5
    fi
    pkill -f 'target/debug/p3_api' 2>/dev/null || true
    sleep 0.3
}

ensure_postgres() {
    if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
        log "starting postgresql"
        service postgresql start
        sleep 2
    else
        log "postgresql already running"
    fi
    if ! PGPASSWORD=p3demo psql -h 127.0.0.1 -U root -d p3demo -c 'select 1' >/dev/null 2>&1; then
        log "provisioning role/db (root superuser, p3demo database)"
        su postgres -c "createuser --superuser root" 2>/dev/null || true
        su postgres -c "createdb p3demo -O root" 2>/dev/null || true
        su postgres -c "psql -c \"ALTER ROLE root WITH PASSWORD 'p3demo';\"" >/dev/null
    fi
}

ensure_venv() {
    if [[ ! -d "$HARNESS_DIR/.venv" ]]; then
        log "creating harness venv"
        python3 -m venv "$HARNESS_DIR/.venv"
    fi
    "$HARNESS_DIR/.venv/bin/pip" install -q -r "$HARNESS_DIR/requirements.txt"
}

build_api() {
    log "building Rust API"
    (cd "$API_DIR" && cargo build --quiet)
}

reset_schema() {
    log "resetting schema to v1-only baseline"
    "$HARNESS_DIR/.venv/bin/python3" "$MIGRATE_DIR/migrate.py" reset
}

start_instances() {
    log "starting v1 (port 3001) and v2 (port 3002)"
    : > "$PIDFILE"
    # Plain background jobs (no setsid): run_demo.sh's own shell stays alive
    # for the whole script, so $! is accurate and cleanup_previous's kill by
    # PID is reliable; pkill -f is only a fallback for a killed/aborted prior
    # run.
    (cd "$API_DIR" && APP_VERSION=1 PORT=3001 DATABASE_URL="$DATABASE_URL" \
        ./target/debug/p3_api </dev/null >/tmp/p3_v1.log 2>&1 &
        echo $! >> "$PIDFILE")
    (cd "$API_DIR" && APP_VERSION=2 PORT=3002 DATABASE_URL="$DATABASE_URL" \
        ./target/debug/p3_api </dev/null >/tmp/p3_v2.log 2>&1 &
        echo $! >> "$PIDFILE")
    sleep 1
    "$HARNESS_DIR/.venv/bin/python3" - <<'PY'
import sys
sys.path.insert(0, "harness")
import common
common.wait_for_health(common.BASE_V1)
common.wait_for_health(common.BASE_V2)
print("both instances healthy")
PY
}

run_tests() {
    log "running Hypothesis stateful conformance test"
    "$HARNESS_DIR/.venv/bin/python3" -m pytest "$HARNESS_DIR/test_stateful.py" -s -v

    log "running concurrent load + migration test"
    "$HARNESS_DIR/.venv/bin/python3" -m pytest "$HARNESS_DIR/test_concurrent.py" -s -v
}

main() {
    cd "$HERE"
    cleanup_previous
    ensure_postgres
    ensure_venv
    build_api
    reset_schema
    start_instances
    run_tests
    log "demo complete -- stopping instances"
    cleanup_previous
}

main "$@"
