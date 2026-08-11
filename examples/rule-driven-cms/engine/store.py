"""SQLite storage. Schema is derived from the rule base (entity fields),
so this module — like the rest of the engine — contains no domain words."""

import sqlite3


def open_db(path, rb, seed_actors=None):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    field_cols = "".join(f", {f} TEXT NOT NULL DEFAULT ''" for f in rb.fields)
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS users (
            name TEXT PRIMARY KEY, role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL, state TEXT NOT NULL{field_cols});
    """)
    for actor in (seed_actors or {}).values():
        if actor.role == "anonymous":
            continue
        conn.execute("INSERT OR REPLACE INTO users (name, role, active) VALUES (?, ?, ?)",
                     (actor.name, actor.role, int(actor.active)))
    conn.commit()
    return conn


def get_user(conn, name):
    return conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()


def get_item(conn, item_id):
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def list_items(conn):
    return conn.execute("SELECT * FROM items ORDER BY id").fetchall()


def create_item(conn, rb, author, state, fields):
    cols = ["author", "state"] + list(rb.fields)
    vals = [author, state] + [fields.get(f, "") for f in rb.fields]
    cur = conn.execute(
        f"INSERT INTO items ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
    conn.commit()
    return cur.lastrowid


def update_item(conn, rb, item_id, updates):
    sets = {k: v for k, v in updates.items() if k in rb.fields or k == "state"}
    if not sets:
        return
    assignment = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(f"UPDATE items SET {assignment} WHERE id = ?", (*sets.values(), item_id))
    conn.commit()


def delete_item(conn, item_id):
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
