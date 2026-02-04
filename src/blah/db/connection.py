"""SQLite database connection and initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db(db_path: Path) -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the database with the full schema."""
    conn = get_db(db_path)
    schema = _SCHEMA_PATH.read_text()
    conn.executescript(schema)
    return conn
