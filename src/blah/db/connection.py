"""SQLite database connection and initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db(db_path: Path) -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_alembic_config(db_path: Path) -> Config:
    """Build an Alembic config pointing at the given database."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def run_migrations(db_path: Path) -> None:
    """Run all pending Alembic migrations."""
    cfg = _get_alembic_config(db_path)
    command.upgrade(cfg, "head")


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the database by running all migrations, return a connection."""
    run_migrations(db_path)
    return get_db(db_path)
