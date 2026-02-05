"""Tests for context CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from blah.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_home(tmp_path: Path) -> Path:
    """Create an initialized BLAH_HOME."""
    home = tmp_path / ".blah"
    home.mkdir()
    (home / "resources").mkdir()

    (home / "config.yaml").write_text(
        "models:\n"
        "  conversation:\n"
        "    provider: anthropic\n"
        "    model: claude-sonnet-4-5\n"
        "context:\n"
        "  path: context.md\n"
        "platforms: {}\n"
    )

    (home / "context.md").write_text(
        "# Context\n\n"
        "## Voice\n"
        "Casual and friendly.\n\n"
        "## Topics\n"
        "Python, AI, startups.\n"
    )

    return home


class TestContextShow:
    def test_context_show_displays_content(self, runner, initialized_home: Path):
        """context show displays the context.md content."""
        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home)}):
            result = runner.invoke(cli, ["context", "show"])

        assert result.exit_code == 0
        assert "Voice" in result.output
        assert "Casual and friendly" in result.output
        assert "Topics" in result.output

    def test_context_show_not_initialized(self, runner, tmp_path: Path):
        """context show fails if not initialized."""
        with patch.dict(os.environ, {"BLAH_HOME": str(tmp_path / "nonexistent")}):
            result = runner.invoke(cli, ["context", "show"])

        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    def test_context_show_empty_context(self, runner, initialized_home: Path):
        """context show handles empty context.md."""
        (initialized_home / "context.md").write_text("")

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home)}):
            result = runner.invoke(cli, ["context", "show"])

        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_context_show_missing_context_file(self, runner, initialized_home: Path):
        """context show handles missing context.md."""
        (initialized_home / "context.md").unlink()

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home)}):
            result = runner.invoke(cli, ["context", "show"])

        assert result.exit_code == 0
        assert "No context.md found" in result.output


class TestContextEdit:
    @patch("subprocess.run")
    def test_context_edit_opens_editor(self, mock_run, runner, initialized_home: Path):
        """context edit opens the editor."""
        mock_run.return_value.returncode = 0

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home), "EDITOR": "nano"}):
            result = runner.invoke(cli, ["context", "edit"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "nano"
        assert "context.md" in call_args[1]

    @patch("subprocess.run")
    def test_context_edit_creates_default_context(self, mock_run, runner, initialized_home: Path):
        """context edit creates default context.md if missing."""
        (initialized_home / "context.md").unlink()
        mock_run.return_value.returncode = 0

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home), "EDITOR": "vim"}):
            result = runner.invoke(cli, ["context", "edit"])

        assert result.exit_code == 0
        # File should be created
        assert (initialized_home / "context.md").exists()
        content = (initialized_home / "context.md").read_text()
        assert "# Context" in content
        assert "## Voice" in content

    @patch("subprocess.run")
    def test_context_edit_uses_visual_fallback(self, mock_run, runner, initialized_home: Path):
        """context edit falls back to VISUAL if EDITOR not set."""
        mock_run.return_value.returncode = 0

        env = {"BLAH_HOME": str(initialized_home), "VISUAL": "code"}
        # Remove EDITOR if present
        env_copy = os.environ.copy()
        env_copy.pop("EDITOR", None)
        env_copy.update(env)

        with patch.dict(os.environ, env_copy, clear=True):
            result = runner.invoke(cli, ["context", "edit"])

        # Should use VISUAL or default to vi
        assert result.exit_code == 0

    @patch("subprocess.run")
    def test_context_edit_editor_not_found(self, mock_run, runner, initialized_home: Path):
        """context edit handles missing editor."""
        mock_run.side_effect = FileNotFoundError("editor not found")

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home), "EDITOR": "nonexistent"}):
            result = runner.invoke(cli, ["context", "edit"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("subprocess.run")
    def test_context_edit_editor_error(self, mock_run, runner, initialized_home: Path):
        """context edit handles editor errors."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "vim")

        with patch.dict(os.environ, {"BLAH_HOME": str(initialized_home), "EDITOR": "vim"}):
            result = runner.invoke(cli, ["context", "edit"])

        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_context_edit_not_initialized(self, runner, tmp_path: Path):
        """context edit fails if not initialized."""
        with patch.dict(os.environ, {"BLAH_HOME": str(tmp_path / "nonexistent")}):
            result = runner.invoke(cli, ["context", "edit"])

        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()
