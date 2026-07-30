"""Shared helpers for the P3 conformance harness.

Talks to the two real running API instances over HTTP and drives the real
migration driver (migrate/migrate.py) as a subprocess -- nothing here is
mocked. This is workflow step 4 from research/07-synthesis.md: "verify
actual system behavior" via model-based testing against the real system.
"""
import os
import subprocess
import sys
import time

import psycopg2
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATE_PY = os.path.normpath(os.path.join(HERE, "..", "migrate", "migrate.py"))

BASE_V1 = os.environ.get("P3_BASE_V1", "http://127.0.0.1:3001")
BASE_V2 = os.environ.get("P3_BASE_V2", "http://127.0.0.1:3002")

DSN = os.environ.get(
    "DATABASE_URL", "host=127.0.0.1 port=5432 dbname=p3demo user=root password=p3demo"
)

MIGRATION_STEPS = ["expand", "install-trigger", "backfill", "read-switch", "contract"]


def run_migrate(*args, timeout=30):
    """Invoke migrate.py as a subprocess (the same driver run_demo.sh uses)."""
    cmd = [sys.executable, MIGRATE_PY, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"migrate.py {' '.join(args)} failed (rc={result.returncode}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout


def run_migrate_step(name, batch_size=None):
    args = ["step", name]
    if name == "backfill" and batch_size is not None:
        args += ["--batch-size", str(batch_size)]
    return run_migrate(*args)


def reset_db():
    run_migrate("reset")


def wait_for_health(base, timeout=15):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=1)
            if r.status_code == 200:
                return
        except requests.RequestException as e:
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"{base} never became healthy: {last_err}")


def create_user(base, name, timeout=5):
    r = requests.post(f"{base}/users", json={"name": name}, timeout=timeout)
    body = _safe_json(r)
    return r.status_code, body


def get_user(base, uid, timeout=5):
    r = requests.get(f"{base}/users/{uid}", timeout=timeout)
    body = _safe_json(r)
    return r.status_code, body


def update_user(base, uid, name, timeout=5):
    r = requests.put(f"{base}/users/{uid}", json={"name": name}, timeout=timeout)
    body = _safe_json(r)
    return r.status_code, body


def _safe_json(r):
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


def is_schema_error(status, body):
    """Detect the F1 'integrity anomaly' symptom: a request failing because
    the column it expects is not (or no longer) present."""
    if status < 500:
        return False
    msg = ""
    if isinstance(body, dict):
        msg = str(body.get("error", ""))
    return "does not exist" in msg


def db_conn():
    return psycopg2.connect(DSN)


def db_users_snapshot():
    """Read the final, unambiguous DB state directly (used only after all
    traffic has quiesced -- see test_concurrent.py)."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' ORDER BY ordinal_position"
            )
            cols = [r[0] for r in cur.fetchall()]
            name_col = "full_name" if "full_name" in cols and "name" not in cols else (
                "COALESCE(full_name, name)" if "full_name" in cols else "name"
            )
            cur.execute(f"SELECT id, {name_col} FROM users ORDER BY id")
            return dict(cur.fetchall())
