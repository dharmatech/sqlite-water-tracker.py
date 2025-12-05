# src/sqlite_water_tracker/ensure_db.py

import sqlite3
from importlib.resources import files

DEFAULT_WEIGHT_LBS = 160.0


def load_schema_text() -> str:
    """Load schema.sql from the installed sqlite_water_tracker package."""
    return (files("sqlite_water_tracker") / "schema.sql").read_text(encoding="utf-8")


def seed_default_weight(conn: sqlite3.Connection, default_weight: float = DEFAULT_WEIGHT_LBS) -> bool:
    """Insert a default weight row if none exist."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_weight")
    row = cur.fetchone()
    if not row or row[0] > 0:
        return False

    cur.execute(
        """
        INSERT INTO user_weight (timestamp, weight_lbs)
        VALUES (datetime('now', 'localtime'), ?)
        """,
        (default_weight,),
    )
    return True


def ensure_db(db_path: str) -> bool:
    """Create the SQLite database schema if needed, otherwise leave it alone.

    Returns True if the DB was modified.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        changed = False

        # Is the main table already there?
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'water_log'
            """
        )
        has_water_log = cur.fetchone() is not None

        if not has_water_log:
            # New or uninitialized DB: apply full schema
            schema_sql = load_schema_text()
            conn.executescript(schema_sql)
            changed = True
            # After schema is in place, seed default weight
            if seed_default_weight(conn):
                changed = True
            conn.commit()
            return changed

        # DB already initialized. Optionally ensure weight is seeded
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'user_weight'
            """
        )
        has_user_weight = cur.fetchone() is not None
        if has_user_weight:
            if seed_default_weight(conn):
                changed = True

        conn.commit()
        return changed
    finally:
        conn.close()
