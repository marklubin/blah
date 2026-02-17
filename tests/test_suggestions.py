"""Tests for suggestion queue: repo CRUD, CLI commands, and agent tools."""

from __future__ import annotations

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from blah.agents.tools.suggestion_tools import SuggestionTools
from blah.cli.main import cli
from blah.db.repository import SuggestionRepo

# ─────────────────────────────────────────────────────────────────
# SuggestionRepo CRUD
# ─────────────────────────────────────────────────────────────────


def test_suggestion_create(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    s = repo.create(idea="Hot take about LLM agents", source="cli", tags=["ai", "agents"])
    assert s["idea"] == "Hot take about LLM agents"
    assert s["source"] == "cli"
    assert s["tags"] == ["ai", "agents"]
    assert s["status"] == "queued"
    assert s["id"] is not None


def test_suggestion_get(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    s = repo.create(idea="Test idea")
    fetched = repo.get(s["id"])
    assert fetched["idea"] == "Test idea"
    assert fetched["source"] == "api"
    assert fetched["tags"] == []


def test_suggestion_get_nonexistent(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    assert repo.get("nonexistent") is None


def test_suggestion_list_by_status(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    repo.create(idea="Queued one")
    repo.create(idea="Queued two")
    s3 = repo.create(idea="Dismissed one")
    repo.update(s3["id"], status="dismissed")

    queued = repo.list_by_status("queued")
    assert len(queued) == 2

    dismissed = repo.list_by_status("dismissed")
    assert len(dismissed) == 1
    assert dismissed[0]["idea"] == "Dismissed one"


def test_suggestion_list_all(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    repo.create(idea="One")
    repo.create(idea="Two")
    assert len(repo.list_all()) == 2


def test_suggestion_update(db: sqlite3.Connection):
    from blah.db.repository import RantRepo

    repo = SuggestionRepo(db)
    rant = RantRepo(db).create(title="Test Rant")
    s = repo.create(idea="Original")
    updated = repo.update(s["id"], status="converted", rant_id=rant["id"])
    assert updated["status"] == "converted"
    assert updated["rant_id"] == rant["id"]


def test_suggestion_delete(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    s = repo.create(idea="Delete me")
    assert repo.delete(s["id"]) is True
    assert repo.get(s["id"]) is None


def test_suggestion_delete_nonexistent(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    assert repo.delete("nonexistent") is False


def test_suggestion_count(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    assert repo.count() == 0
    repo.create(idea="One")
    repo.create(idea="Two")
    assert repo.count() == 2


def test_suggestion_count_by_status(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    repo.create(idea="One")
    s2 = repo.create(idea="Two")
    repo.update(s2["id"], status="dismissed")
    assert repo.count(status="queued") == 1
    assert repo.count(status="dismissed") == 1


# ─────────────────────────────────────────────────────────────────
# CLI commands
# ─────────────────────────────────────────────────────────────────


def test_suggest_command(tmp_path):
    """blah rant suggest adds a suggestion directly."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "suggest", "LLM agents are overhyped"])
    assert result.exit_code == 0
    assert "Added suggestion" in result.output


def test_suggestions_list_empty(tmp_path):
    """blah rant suggestions shows empty message when no suggestions."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "suggestions"])
    assert result.exit_code == 0
    assert "No suggestions" in result.output


def test_suggestions_list_with_data(tmp_path):
    """blah rant suggestions lists suggestions after adding one."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["rant", "suggest", "AI hot take"])
        result = runner.invoke(cli, ["rant", "suggestions"])
    assert result.exit_code == 0
    assert "AI hot take" in result.output


def test_pull_suggestions_not_configured(tmp_path):
    """blah rant pull-suggestions fails when queue not configured."""
    home = tmp_path / ".blah"
    runner = CliRunner()
    with patch.dict(os.environ, {"BLAH_HOME": str(home)}):
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["rant", "pull-suggestions"])
    assert result.exit_code == 1
    assert "Queue not configured" in result.output


def _enable_queue(home):
    """Helper to enable queue config in a test home."""
    import yaml

    config_path = home / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["queue"] = {
        "enabled": True,
        "account_id": "test-account",
        "kv_namespace_id": "test-ns",
        "api_token": "test-token",
    }
    config_path.write_text(yaml.dump(config))


def test_pull_suggestions_empty_queue(tmp_path):
    """blah rant pull-suggestions reports when queue is empty."""
    home = tmp_path / ".blah"
    runner = CliRunner()

    list_resp = MagicMock()
    list_resp.json.return_value = {"result": []}
    list_resp.raise_for_status = MagicMock()

    with (
        patch.dict(os.environ, {"BLAH_HOME": str(home)}),
        patch("blah.cli.commands.rant.httpx.get", return_value=list_resp),
    ):
        runner.invoke(cli, ["init"])
        _enable_queue(home)
        result = runner.invoke(cli, ["rant", "pull-suggestions"])

    assert result.exit_code == 0
    assert "No new suggestions" in result.output


def test_pull_suggestions_with_messages(tmp_path):
    """blah rant pull-suggestions stores KV entries and deletes them."""
    home = tmp_path / ".blah"
    runner = CliRunner()

    list_resp = MagicMock()
    list_resp.json.return_value = {
        "result": [{"name": "key-1"}, {"name": "key-2"}]
    }
    list_resp.raise_for_status = MagicMock()

    val1 = MagicMock()
    val1.status_code = 200
    val1.json.return_value = {"idea": "Hot take 1", "source": "api", "tags": ["ai"]}

    val2 = MagicMock()
    val2.status_code = 200
    val2.json.return_value = {"idea": "Hot take 2", "source": "phone", "tags": []}

    get_calls = iter([list_resp, val1, val2])
    delete_resp = MagicMock()

    with (
        patch.dict(os.environ, {"BLAH_HOME": str(home)}),
        patch("blah.cli.commands.rant.httpx.get", side_effect=lambda *a, **kw: next(get_calls)),
        patch("blah.cli.commands.rant.httpx.delete", return_value=delete_resp),
    ):
        runner.invoke(cli, ["init"])
        _enable_queue(home)
        result = runner.invoke(cli, ["rant", "pull-suggestions"])

    assert result.exit_code == 0
    assert "Pulled 2 suggestion(s)" in result.output


# ─────────────────────────────────────────────────────────────────
# Agent tools
# ─────────────────────────────────────────────────────────────────


def test_tool_list_suggestions(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    repo.create(idea="Idea 1", source="api")
    repo.create(idea="Idea 2", source="cli")

    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.list_suggestions()
    data = json.loads(result.content)
    assert data["total"] == 2
    assert not result.is_error


def test_tool_get_suggestion(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    s = repo.create(idea="Test idea")

    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.get_suggestion(s["id"])
    data = json.loads(result.content)
    assert data["idea"] == "Test idea"
    assert not result.is_error


def test_tool_get_suggestion_not_found(db: sqlite3.Connection):
    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.get_suggestion("nonexistent")
    assert result.is_error


def test_tool_convert_suggestion(db: sqlite3.Connection):
    from blah.db.repository import RantRepo

    rant = RantRepo(db).create(title="Test Rant")
    repo = SuggestionRepo(db)
    s = repo.create(idea="Convert me")

    tools = SuggestionTools(db, rant_id=rant["id"])
    result = tools.convert_suggestion(s["id"])
    data = json.loads(result.content)
    assert data["status"] == "converted"
    assert data["rant_id"] == rant["id"]

    # Verify in DB
    updated = repo.get(s["id"])
    assert updated["status"] == "converted"
    assert updated["rant_id"] == rant["id"]


def test_tool_dismiss_suggestion(db: sqlite3.Connection):
    repo = SuggestionRepo(db)
    s = repo.create(idea="Dismiss me")

    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.dismiss_suggestion(s["id"])
    data = json.loads(result.content)
    assert data["status"] == "dismissed"

    # No longer in queued list
    assert repo.count(status="queued") == 0
    assert repo.count(status="dismissed") == 1


def test_tool_convert_nonexistent(db: sqlite3.Connection):
    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.convert_suggestion("nonexistent")
    assert result.is_error


def test_tool_dismiss_nonexistent(db: sqlite3.Connection):
    tools = SuggestionTools(db, rant_id="test-rant")
    result = tools.dismiss_suggestion("nonexistent")
    assert result.is_error
