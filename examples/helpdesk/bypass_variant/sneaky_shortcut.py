"""The counterexample the boundary lint exists for — PRESERVED, NEVER RUN.

A plausible 'quick win' an agent (or a hurried human) might write into the
UI layer: end-of-quarter cleanup that closes stale cases directly in the
database, skipping the kernel — and with it lead-only closing (S11), the
resolution seal (S9), and the closed-forever record (S10). Nothing here is
exotic; it is three lines of ordinary Python. That is exactly why the
boundary must be held by a named CI failure and not by code review:
check.sh runs `python -m analysis.boundary bypass_variant/` and REQUIRES
it to fail on this file.
"""

import sqlite3                     # FAIL: the store's substrate

from engine import store           # FAIL: beneath the boundary


def close_stale_cases(db_path):
    conn = sqlite3.connect(db_path)
    for row in store.list_items(conn):
        conn.execute("UPDATE items SET state = 'closed' WHERE id = ?",
                     (row["id"],))
    conn.commit()
