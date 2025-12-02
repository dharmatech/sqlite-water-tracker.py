# src/sqlite_water_tracker/ensure_db.py

import sqlite3
from importlib.resources import files


def load_schema_text() -> str:
    """Load schema.sql from the installed sqlite_water_tracker package."""
    return (files("sqlite_water_tracker") / "schema.sql").read_text(encoding="utf-8")


def ensure_db(db_path: str) -> None:
    """Create / update the SQLite database schema if needed."""
    conn = sqlite3.connect(db_path)
    try:
        schema_sql = load_schema_text()
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
