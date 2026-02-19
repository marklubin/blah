"""Tests for the `blah radar health` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from blah.cli.commands.radar import radar
from blah.db.connection import init_db
from blah.db.repository import SourceRepo


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def health_env(tmp_path: Path):
    """Set up a temporary BLAH_HOME with initialized DB for health tests."""
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
        "  max_tokens: 2000\n"
        "platforms: {}\n"
    )
    (home / "context.md").write_text("# Context\n")

    # Initialize the DB so tables exist
    conn = init_db(home / "blah.db")
    conn.close()

    return home


def _patch_all_adapters(**overrides):
    """Return a combined context manager that patches all 5 adapter classes.

    Each adapter defaults to a MagicMock whose authenticate() is a no-op.
    Pass keyword args like ``BlueskyAdapter=my_mock`` to override specific ones.
    """
    from contextlib import ExitStack

    adapter_paths = {
        "BlueskyAdapter": "blah.adapters.bluesky.BlueskyAdapter",
        "TwitterAdapter": "blah.adapters.twitter.TwitterAdapter",
        "RedditAdapter": "blah.adapters.reddit.RedditAdapter",
        "HackerNewsAdapter": "blah.adapters.hackernews.HackerNewsAdapter",
        "DiscordAdapter": "blah.adapters.discord.DiscordAdapter",
    }

    class _PatchContext:
        def __init__(self):
            self._stack = ExitStack()
            self.mocks = {}

        def __enter__(self):
            self._stack.__enter__()
            for name, path in adapter_paths.items():
                if name in overrides:
                    mock_cls = self._stack.enter_context(
                        patch(path, overrides[name])
                    )
                else:
                    mock_cls = self._stack.enter_context(patch(path))
                    mock_cls.return_value = MagicMock()
                self.mocks[name] = mock_cls
            return self

        def __exit__(self, *exc):
            return self._stack.__exit__(*exc)

    return _PatchContext()


class TestRadarHealthAllDisabled:
    """Health command when all platforms are disabled."""

    def test_all_disabled(self, runner, health_env, monkeypatch):
        """All platforms show as disabled with no connectivity check."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        with _patch_all_adapters():
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "Radar Health Check" in result.output
        assert "bluesky" in result.output
        assert "twitter" in result.output
        assert "reddit" in result.output
        assert "hackernews" in result.output
        assert "discord" in result.output
        assert "linkedin" in result.output


class TestRadarHealthBluesky:
    """Health command with bluesky enabled and mocked adapter."""

    def test_bluesky_ok(self, runner, health_env, monkeypatch):
        """Bluesky shows OK when authenticate() succeeds."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  bluesky:\n"
            "    enabled: true\n"
            "    handle: test.bsky.social\n"
            "    app_password: test-password\n"
        )

        mock_bsky_cls = MagicMock()
        mock_bsky_instance = MagicMock()
        mock_bsky_cls.return_value = mock_bsky_instance

        with _patch_all_adapters(BlueskyAdapter=mock_bsky_cls):
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "OK" in result.output
        mock_bsky_cls.assert_called_once_with(
            handle="test.bsky.social", app_password="test-password"
        )
        mock_bsky_instance.authenticate.assert_called_once()

    def test_bluesky_auth_failure(self, runner, health_env, monkeypatch):
        """Bluesky shows FAIL when authenticate() raises."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  bluesky:\n"
            "    enabled: true\n"
            "    handle: test.bsky.social\n"
            "    app_password: bad-password\n"
        )

        mock_bsky_cls = MagicMock()
        mock_bsky_instance = MagicMock()
        mock_bsky_instance.authenticate.side_effect = RuntimeError("invalid token")
        mock_bsky_cls.return_value = mock_bsky_instance

        with _patch_all_adapters(BlueskyAdapter=mock_bsky_cls):
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "FAIL" in result.output
        assert "invalid token" in result.output


class TestRadarHealthSourceCount:
    """Health command counts sources per platform."""

    def test_source_counting(self, runner, health_env, monkeypatch):
        """Sources column shows correct count per platform."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        # Add some sources to the DB
        conn = init_db(health_env / "blah.db")
        try:
            source_repo = SourceRepo(conn)
            source_repo.create("bluesky", "timeline", {"label": "Timeline"})
            source_repo.create("bluesky", "account", {"handle": "test", "label": "@test"})
            source_repo.create("reddit", "subreddit", {"subreddit": "python", "label": "r/python"})
        finally:
            conn.close()

        with _patch_all_adapters():
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "2" in result.output  # bluesky sources
        assert "1" in result.output  # reddit sources


class TestRadarHealthHackerNews:
    """Health command for HackerNews (no credentials needed)."""

    def test_hackernews_enabled_ok(self, runner, health_env, monkeypatch):
        """HackerNews shows OK when enabled (no credentials needed)."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  hackernews:\n"
            "    enabled: true\n"
        )

        mock_hn_cls = MagicMock()
        mock_hn_cls.return_value = MagicMock()

        with _patch_all_adapters(HackerNewsAdapter=mock_hn_cls):
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "OK" in result.output


class TestRadarHealthLinkedin:
    """Health command for LinkedIn (browser-only, n/a)."""

    def test_linkedin_shows_na(self, runner, health_env, monkeypatch):
        """LinkedIn always shows n/a for connectivity."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  linkedin:\n"
            "    enabled: true\n"
        )

        with _patch_all_adapters():
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "n/a" in result.output


class TestRadarHealthDiscord:
    """Health command for Discord (via MCP router)."""

    def test_discord_ok(self, runner, health_env, monkeypatch):
        """Discord shows OK when router is reachable."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))
        monkeypatch.setenv("ROUTER_PORT", "9999")

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  discord:\n"
            "    enabled: true\n"
        )

        mock_dc_cls = MagicMock()
        mock_dc_cls.return_value = MagicMock()

        with _patch_all_adapters(DiscordAdapter=mock_dc_cls):
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "OK" in result.output
        mock_dc_cls.assert_called_once_with(router_url="http://127.0.0.1:9999")

    def test_discord_fail(self, runner, health_env, monkeypatch):
        """Discord shows FAIL when router is unreachable."""
        monkeypatch.setenv("BLAH_HOME", str(health_env))

        (health_env / "config.yaml").write_text(
            "models:\n"
            "  conversation:\n"
            "    provider: anthropic\n"
            "    model: claude-sonnet-4-5\n"
            "context:\n"
            "  path: context.md\n"
            "  max_tokens: 2000\n"
            "platforms:\n"
            "  discord:\n"
            "    enabled: true\n"
        )

        mock_dc_cls = MagicMock()
        mock_dc_instance = MagicMock()
        mock_dc_instance.authenticate.side_effect = ConnectionError("router down")
        mock_dc_cls.return_value = mock_dc_instance

        with _patch_all_adapters(DiscordAdapter=mock_dc_cls):
            result = runner.invoke(radar, ["health"])

        assert result.exit_code == 0
        assert "FAIL" in result.output
        assert "router down" in result.output
