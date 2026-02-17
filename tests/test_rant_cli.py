"""Tests for rant CLI commands."""

from __future__ import annotations

import os
from unittest.mock import patch

from click.testing import CliRunner

from blah.cli.main import cli


def test_rant_list_empty(tmp_path):
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "list"])
    assert result.exit_code == 0
    assert "No rants" in result.output


def test_rant_show_not_found(tmp_path):
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "show", "nonexistent"])
    assert result.exit_code == 1


def test_rant_list_with_rant(tmp_path):
    """List shows rants after creating one directly in the DB."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])

        # Create a rant directly
        from blah.db.connection import get_db
        from blah.db.repository import RantRepo

        conn = get_db(home / "blah.db")
        RantRepo(conn).create(title="Test Rant")
        conn.close()

        result = runner.invoke(cli, ["rant", "list"])

    assert result.exit_code == 0
    assert "Test Rant" in result.output


def test_rant_show_with_pieces(tmp_path):
    """Show displays rant details and pieces."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])

        from blah.db.connection import get_db
        from blah.db.repository import PieceRepo, RantRepo

        conn = get_db(home / "blah.db")
        rant = RantRepo(conn).create(title="Test Rant", summary="About testing")
        PieceRepo(conn).create(
            rant_id=rant["id"], platform="bluesky", content="Hello Bluesky!"
        )
        conn.close()

        result = runner.invoke(cli, ["rant", "show", rant["id"]])

    assert result.exit_code == 0
    assert "Test Rant" in result.output
    assert "About testing" in result.output
    assert "bluesky" in result.output
    assert "Hello Bluesky!" in result.output


def test_rant_chat_not_found(tmp_path):
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "chat", "nonexistent"])
    assert result.exit_code == 1
