"""SQLite storage. Schema is derived from the rule base (entity fields),
so this module — like the rest of the engine — contains no domain words.

One table per entity: the root entity keeps the historical `items` table;
each child entity gets `items_<entity>` with a `parent_id` column pointing
at its root row. Deleting a root row deletes its children with it — the
children's own delete rules are NOT consulted on that path, which is why a
rule base that must never lose children should not allow deleting the
parent either (see research note 16, the cascade sharp edge)."""

import sqlite3

from . import rulebase as rb_mod


def _table(rb, entity=None):
    ent = rb.entity_of(entity)
    return "items" if ent is rb.root else f"items_{ent.name}"


def open_db(path, rb, seed_actors=None):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    actor_cols = "".join(f", {f} TEXT NOT NULL DEFAULT ''" for f in rb.actor_fields)
    ddl = [f"""
        CREATE TABLE IF NOT EXISTS users (
            name TEXT PRIMARY KEY, role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1{actor_cols});"""]
    for ent in rb.entities.values():
        field_cols = "".join(f", {f} TEXT NOT NULL DEFAULT ''" for f in ent.fields)
        parent_col = ", parent_id INTEGER NOT NULL" if ent.parent else ""
        ddl.append(f"""
        CREATE TABLE IF NOT EXISTS {_table(rb, ent.name)} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL, state TEXT NOT NULL{parent_col}{field_cols});""")
    conn.executescript("".join(ddl))
    for actor in (seed_actors or {}).values():
        if actor.role == "anonymous":
            continue
        cols = ["name", "role", "active"] + list(rb.actor_fields)
        vals = [actor.name, actor.role, int(actor.active)] \
            + [str(actor.attrs.get(f, "")) for f in rb.actor_fields]
        conn.execute(f"INSERT OR REPLACE INTO users ({', '.join(cols)}) "
                     f"VALUES ({', '.join('?' * len(cols))})", vals)
    conn.commit()
    return conn


def get_user(conn, name):
    return conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()


def list_users(conn):
    return conn.execute("SELECT * FROM users ORDER BY role, name").fetchall()


def get_item(conn, rb, item_id, entity=None):
    return conn.execute(f"SELECT * FROM {_table(rb, entity)} WHERE id = ?",
                        (item_id,)).fetchone()


def list_items(conn, rb, entity=None, parent_id=None):
    table = _table(rb, entity)
    if parent_id is None:
        return conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    return conn.execute(f"SELECT * FROM {table} WHERE parent_id = ? ORDER BY id",
                        (parent_id,)).fetchall()


def create_item(conn, rb, author, state, fields, entity=None, parent_id=None):
    ent = rb.entity_of(entity)
    cols = ["author", "state"] + list(ent.fields)
    vals = [author, state] + [fields.get(f, "") for f in ent.fields]
    if ent.parent:
        cols.append("parent_id")
        vals.append(int(parent_id))
    cur = conn.execute(
        f"INSERT INTO {_table(rb, entity)} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})", vals)
    conn.commit()
    return cur.lastrowid


def update_item(conn, rb, item_id, updates, entity=None):
    ent = rb.entity_of(entity)
    sets = {k: v for k, v in updates.items() if k in ent.fields or k == "state"}
    if not sets:
        return
    assignment = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(f"UPDATE {_table(rb, entity)} SET {assignment} WHERE id = ?",
                 (*sets.values(), item_id))
    conn.commit()


def delete_item(conn, rb, item_id, entity=None):
    ent = rb.entity_of(entity)
    if ent is rb.root:
        for child in rb.entities.values():
            if child.parent:
                conn.execute(f"DELETE FROM {_table(rb, child.name)} "
                             f"WHERE parent_id = ?", (item_id,))
    conn.execute(f"DELETE FROM {_table(rb, entity)} WHERE id = ?", (item_id,))
    conn.commit()
