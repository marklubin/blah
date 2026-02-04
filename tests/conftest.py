"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from blah.config.settings import BlahSettings
from blah.db.connection import init_db


@pytest.fixture
def tmp_blah_home(tmp_path: Path) -> Path:
    """Create a temporary BLAH_HOME directory with default files."""
    home = tmp_path / ".blah"
    home.mkdir()
    (home / "resources").mkdir()

    (home / "config.yaml").write_text(
        "models:\n"
        "  conversation:\n"
        "    provider: anthropic\n"
        "    model: claude-sonnet-4-5-20250514\n"
        "context:\n"
        "  path: context.md\n"
        "  max_tokens: 2000\n"
        "platforms: {}\n"
    )

    (home / "context.md").write_text("# Context\n\n## Voice\nTest voice.\n")

    return home


@pytest.fixture
def db(tmp_blah_home: Path) -> sqlite3.Connection:
    """Initialize and return a test database connection."""
    conn = init_db(tmp_blah_home / "blah.db")
    yield conn
    conn.close()


@pytest.fixture
def settings(tmp_blah_home: Path) -> BlahSettings:
    """Load settings from the temporary BLAH_HOME."""
    return BlahSettings.load(blah_home=tmp_blah_home)
