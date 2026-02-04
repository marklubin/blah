"""Tests for basic CLI commands: --help, init, status."""

from __future__ import annotations

import os
from unittest.mock import patch

from click.testing import CliRunner

from blah.cli.main import cli


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Makes noise" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init(tmp_path):
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert home.exists()
    assert (home / "config.yaml").exists()
    assert (home / "context.md").exists()
    assert (home / "blah.db").exists()
    assert (home / "resources").exists()


def test_init_already_exists(tmp_path):
    home = tmp_path / ".blah"
    home.mkdir()
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_status(tmp_path):
    home = tmp_path / ".blah"
    runner = CliRunner()
    # First init
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "BLAH_HOME" in result.output


def test_status_not_initialized(tmp_path):
    home = tmp_path / ".blah_nonexistent"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 1


def test_rant_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["rant", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "list" in result.output
    assert "show" in result.output
    assert "publish" in result.output


def test_radar_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["radar", "--help"])
    assert result.exit_code == 0
    assert "config" in result.output
    assert "pull" in result.output
    assert "report" in result.output


def test_context_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["context", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "edit" in result.output


def test_config_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "credentials" in result.output
