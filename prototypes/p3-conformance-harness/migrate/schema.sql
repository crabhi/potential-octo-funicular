-- Baseline ("v1-only") schema. Applied by `migrate.py reset`.
--
-- `users.name` is the sole source of truth. The migration in migrate.py
-- expands this into `full_name` via a trigger + backfill, flips reads, then
-- contracts (drops the trigger and `name`).

DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS migration_state CASCADE;
DROP FUNCTION IF EXISTS users_propagate_full_name();

CREATE TABLE users (
    id serial PRIMARY KEY,
    name text NOT NULL
);

-- Single-row control table the app polls per-request (see api/src/main.rs
-- migration_flags()) to decide how to read/write during the migration.
CREATE TABLE migration_state (
    id int PRIMARY KEY DEFAULT 1,
    phase text NOT NULL DEFAULT 'v1-only',
    dual_write boolean NOT NULL DEFAULT false,
    read_switch boolean NOT NULL DEFAULT false,
    contracted boolean NOT NULL DEFAULT false
);
INSERT INTO migration_state (id) VALUES (1);
