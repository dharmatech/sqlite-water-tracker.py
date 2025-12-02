# src/sqlite_water_tracker/ensure_db.py

import sqlite3
from importlib.resources import files

DEFAULT_WEIGHT_LBS = 160.0


def load_schema_text() -> str:
    """Load schema.sql from the installed sqlite_water_tracker package."""
    return (files("sqlite_water_tracker") / "schema.sql").read_text(encoding="utf-8")


def seed_default_weight(conn: sqlite3.Connection, default_weight: float = DEFAULT_WEIGHT_LBS) -> None:
    """Insert a default weight row if none exist."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_weight")
    row = cur.fetchone()
    if not row or row[0] > 0:
        return

    cur.execute(
        """
        INSERT INTO user_weight (timestamp, weight_lbs)
        VALUES (datetime('now', 'localtime'), ?)
        """,
        (default_weight,),
    )
    conn.commit()


def ensure_db(db_path: str) -> None:
    """Create / update the SQLite database schema if needed."""
    conn = sqlite3.connect(db_path)
    try:
        schema_sql = load_schema_text()
        conn.executescript(schema_sql)
        seed_default_weight(conn)
        conn.commit()
    finally:
        conn.close()
