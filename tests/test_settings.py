"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from blah.config.settings import BlahSettings


def test_load_from_config_yaml(tmp_blah_home: Path):
    settings = BlahSettings.load(blah_home=tmp_blah_home)
    assert settings.blah_home == tmp_blah_home
    assert settings.models.conversation.provider == "anthropic"
    assert settings.context.max_tokens == 2000


def test_paths(tmp_blah_home: Path):
    settings = BlahSettings.load(blah_home=tmp_blah_home)
    assert settings.db_path == tmp_blah_home / "blah.db"
    assert settings.config_path == tmp_blah_home / "config.yaml"
    assert settings.context_path == tmp_blah_home / "context.md"
    assert settings.resources_path == tmp_blah_home / "resources"


def test_defaults():
    """Settings should work with all defaults when no config file exists."""
    settings = BlahSettings(blah_home=Path("/tmp/test-blah-nonexistent"))
    assert settings.models.triage.model == "claude-3-haiku-20240307"
    assert settings.models.conversation.model == "claude-sonnet-4-20250514"
    assert settings.context.path == "context.md"


def test_load_empty_config(tmp_path: Path):
    home = tmp_path / ".blah"
    home.mkdir()
    (home / "config.yaml").write_text("")
    settings = BlahSettings.load(blah_home=home)
    assert settings.blah_home == home
