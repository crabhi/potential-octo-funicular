#!/usr/bin/env python3
"""Migration driver for P3: expand/contract rename of users.name -> full_name.

Implements the F1-style decomposition from research/05-db-migrations-concurrency.md
("## How to model it") as a sequence of individually-invokable steps, each its
own transaction (backfill = one transaction per batch):

  expand           -> ALTER TABLE users ADD COLUMN full_name text
  install-trigger  -> BEFORE INSERT OR UPDATE trigger mirrors name -> full_name
                      on every write, from *either* app version (this is what
                      lets v1 instances -- which only ever touch `name` --
                      keep working correctly through backfill/read-switch)
  backfill         -> UPDATE ... WHERE full_name IS NULL ... LIMIT n, looped
                      (only needed for rows that existed before the trigger)
  read-switch      -> flip migration_state.read_switch = true
  contract         -> drop trigger, drop `name` column

Each step updates migration_state.phase / dual_write / read_switch / contracted
so the running API instances (which poll this table per request) observe the
new state on their very next query -- no restart required.

Usage:
    python3 migrate.py reset
    python3 migrate.py status
    python3 migrate.py step expand
    python3 migrate.py step install-trigger
    python3 migrate.py step backfill [--batch-size N]
    python3 migrate.py step read-switch
    python3 migrate.py step contract
    python3 migrate.py run-all [--with-traffic-pause-ms N] [--batch-size N]
"""
import argparse
import os
import sys
import time

import psycopg2

DSN = os.environ.get(
    "DATABASE_URL", "host=127.0.0.1 port=5432 dbname=p3demo user=root password=p3demo"
)
SCHEMA_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

STEP_ORDER = ["expand", "install-trigger", "backfill", "read-switch", "contract"]


def connect():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    return conn


def log(msg):
    print(f"[migrate] {msg}", flush=True)


def do_reset(conn):
    with open(SCHEMA_SQL) as f:
        sql = f.read()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    log("reset: schema recreated (v1-only: users(id, name))")


def do_status(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT phase, dual_write, read_switch, contracted FROM migration_state WHERE id = 1"
            )
            row = cur.fetchone()
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' ORDER BY ordinal_position"
            )
            cols = [r[0] for r in cur.fetchall()]
    if row is None:
        print("no migration_state row (schema not initialized -- run `reset` first)")
        return
    phase, dual_write, read_switch, contracted = row
    print(f"phase={phase} dual_write={dual_write} read_switch={read_switch} contracted={contracted}")
    print(f"users columns: {cols}")


def step_expand(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name text")
            cur.execute("UPDATE migration_state SET phase = 'expand' WHERE id = 1")
    log("expand: added users.full_name (nullable)")


def step_install_trigger(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION users_propagate_full_name()
                RETURNS trigger AS $$
                BEGIN
                    NEW.full_name := NEW.name;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
            cur.execute("DROP TRIGGER IF EXISTS trg_propagate_full_name ON users")
            cur.execute(
                """
                CREATE TRIGGER trg_propagate_full_name
                BEFORE INSERT OR UPDATE ON users
                FOR EACH ROW EXECUTE FUNCTION users_propagate_full_name();
                """
            )
            cur.execute(
                "UPDATE migration_state SET phase = 'trigger-installed', dual_write = true WHERE id = 1"
            )
    log(
        "install-trigger: BEFORE trigger now mirrors name -> full_name on every "
        "write (from v1 or v2); dual_write=true"
    )


def step_backfill(conn, batch_size=50):
    total = 0
    while True:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET full_name = name "
                    "WHERE id IN (SELECT id FROM users WHERE full_name IS NULL ORDER BY id LIMIT %s) "
                    "RETURNING id",
                    (batch_size,),
                )
                n = cur.rowcount
        total += n
        log(f"backfill: batch updated {n} row(s) (running total {total})")
        if n == 0:
            break
        time.sleep(0.05)
    with conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE migration_state SET phase = 'backfilled' WHERE id = 1")
    log(f"backfill: complete, {total} historical row(s) filled")


def step_read_switch(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE migration_state SET read_switch = true, phase = 'read-switch' WHERE id = 1"
            )
    log("read-switch: read_switch=true (v2 now reads full_name)")


def step_contract(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_propagate_full_name ON users")
            cur.execute("DROP FUNCTION IF EXISTS users_propagate_full_name()")
    with conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE users DROP COLUMN name")
            cur.execute(
                "UPDATE migration_state SET phase = 'contracted', dual_write = false, "
                "contracted = true WHERE id = 1"
            )
    log("contract: dropped trigger + users.name (only full_name remains)")


STEPS = {
    "expand": step_expand,
    "install-trigger": step_install_trigger,
    "backfill": step_backfill,
    "read-switch": step_read_switch,
    "contract": step_contract,
}


def run_step(conn, name, batch_size=50):
    if name == "backfill":
        step_backfill(conn, batch_size)
    else:
        STEPS[name](conn)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reset")
    sub.add_parser("status")

    step_p = sub.add_parser("step")
    step_p.add_argument("name", choices=STEP_ORDER)
    step_p.add_argument("--batch-size", type=int, default=50)

    run_p = sub.add_parser("run-all")
    run_p.add_argument("--with-traffic-pause-ms", type=int, default=0)
    run_p.add_argument("--batch-size", type=int, default=50)

    args = ap.parse_args()
    conn = connect()
    try:
        if args.cmd == "reset":
            do_reset(conn)
        elif args.cmd == "status":
            do_status(conn)
        elif args.cmd == "step":
            run_step(conn, args.name, getattr(args, "batch_size", 50))
        elif args.cmd == "run-all":
            for name in STEP_ORDER:
                run_step(conn, name, args.batch_size)
                if args.with_traffic_pause_ms:
                    time.sleep(args.with_traffic_pause_ms / 1000.0)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
