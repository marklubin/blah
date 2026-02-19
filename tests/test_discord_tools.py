"""Tests for Discord tools."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

from blah.agents.tools.discord_tools import DiscordTools
from blah.db.repository import FeedItemRepo, SourceRepo


def _mock_discord_adapter():
    """Create a mock Discord adapter."""
    adapter = MagicMock()
    adapter.platform_name = "discord"
    return adapter


class TestListDiscordServers:
    """Tests for list_discord_servers tool."""

    def test_no_adapter(self, db: sqlite3.Connection):
        """Returns error when no adapter configured."""
        tools = DiscordTools(db, adapter=None)

        result = tools.list_discord_servers()

        assert result.is_error
        assert "not configured" in result.content

    def test_list_servers(self, db: sqlite3.Connection):
        """Returns server list from adapter."""
        adapter = _mock_discord_adapter()
        adapter.get_guilds.return_value = [
            {"id": "g1", "name": "My Server", "owner": True},
            {"id": "g2", "name": "Other Server", "owner": False},
        ]
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_servers()

        assert not result.is_error
        assert "My Server" in result.content
        assert "(owner)" in result.content
        assert "Other Server" in result.content
        assert "g1" in result.content
        adapter.get_guilds.assert_called_once()

    def test_no_servers(self, db: sqlite3.Connection):
        """Returns message when no servers found."""
        adapter = _mock_discord_adapter()
        adapter.get_guilds.return_value = []
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_servers()

        assert not result.is_error
        assert "No servers" in result.content

    def test_adapter_error(self, db: sqlite3.Connection):
        """Returns error on adapter failure."""
        adapter = _mock_discord_adapter()
        adapter.get_guilds.side_effect = Exception("API error")
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_servers()

        assert result.is_error
        assert "Failed" in result.content


class TestListDiscordChannels:
    """Tests for list_discord_channels tool."""

    def test_no_adapter(self, db: sqlite3.Connection):
        """Returns error when no adapter configured."""
        tools = DiscordTools(db, adapter=None)

        result = tools.list_discord_channels(server_id="g1")

        assert result.is_error
        assert "not configured" in result.content

    def test_list_channels(self, db: sqlite3.Connection):
        """Returns channel list from adapter."""
        adapter = _mock_discord_adapter()
        adapter.get_guild_channels.return_value = [
            {"id": "c1", "name": "general", "type": 0, "position": 0, "parent_id": None},
            {"id": "c2", "name": "updates", "type": 5, "position": 1, "parent_id": None},
        ]
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_channels(server_id="g1")

        assert not result.is_error
        assert "#general" in result.content
        assert "#updates" in result.content
        assert "text" in result.content
        assert "announcement" in result.content
        adapter.get_guild_channels.assert_called_once_with("g1")

    def test_no_channels(self, db: sqlite3.Connection):
        """Returns message when no channels found."""
        adapter = _mock_discord_adapter()
        adapter.get_guild_channels.return_value = []
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_channels(server_id="g1")

        assert not result.is_error
        assert "No text channels" in result.content

    def test_adapter_error(self, db: sqlite3.Connection):
        """Returns error on adapter failure."""
        adapter = _mock_discord_adapter()
        adapter.get_guild_channels.side_effect = Exception("forbidden")
        tools = DiscordTools(db, adapter=adapter)

        result = tools.list_discord_channels(server_id="g1")

        assert result.is_error
        assert "Failed" in result.content


class TestStoreDiscordItems:
    """Tests for store_discord_items tool."""

    def test_store_discord_items(self, db: sqlite3.Connection):
        """Stores items and returns correct counts."""
        tools = DiscordTools(db)

        items = [
            {"external_id": "msg-1", "author": "Alice", "text": "Hello world", "url": "https://discord.com/channels/111/222/333"},
            {"external_id": "msg-2", "author": "Bob", "text": "Another message", "url": "https://discord.com/channels/111/222/444"},
        ]

        result = tools.store_discord_items(json.dumps(items))

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert data["ingested"] == 2
        assert data["skipped"] == 0
        assert "source_id" in data

        # Verify items are in DB
        feed_repo = FeedItemRepo(db)
        item = feed_repo.get_by_external_id("discord", "msg-1")
        assert item is not None
        assert item["author"] == "Alice"
        assert item["content"] == "Hello world"

    def test_store_discord_items_dedup(self, db: sqlite3.Connection):
        """Duplicate items are skipped."""
        tools = DiscordTools(db)

        items = [
            {"external_id": "msg-1", "author": "Alice", "text": "Hello world"},
        ]

        # First insert
        result1 = tools.store_discord_items(json.dumps(items))
        data1 = json.loads(result1.content)
        assert data1["ingested"] == 1

        # Second insert - should be skipped
        result2 = tools.store_discord_items(json.dumps(items))
        data2 = json.loads(result2.content)
        assert data2["ingested"] == 0
        assert data2["skipped"] == 1

    def test_store_discord_items_invalid_json(self, db: sqlite3.Connection):
        """Returns error for invalid JSON."""
        tools = DiscordTools(db)

        result = tools.store_discord_items("not valid json{{{")

        assert result.is_error
        assert "Invalid JSON" in result.content

    def test_store_discord_items_not_array(self, db: sqlite3.Connection):
        """Returns error when input is not an array."""
        tools = DiscordTools(db)

        result = tools.store_discord_items('{"key": "value"}')

        assert result.is_error
        assert "JSON array" in result.content


class TestGetDiscordSources:
    """Tests for get_discord_sources tool."""

    def test_get_discord_sources_empty(self, db: sqlite3.Connection):
        """Returns message when no sources configured."""
        tools = DiscordTools(db)

        result = tools.get_discord_sources()

        assert not result.is_error
        assert "No Discord sources" in result.content

    def test_get_discord_sources_with_data(self, db: sqlite3.Connection):
        """Shows sources when they exist."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="discord",
            source_type="channel",
            config={"label": "#general in My Server", "channel_id": "12345"},
        )

        tools = DiscordTools(db)

        result = tools.get_discord_sources()

        assert not result.is_error
        assert "Discord sources:" in result.content
        assert "#general in My Server" in result.content
        assert "channel" in result.content
        assert "12345" in result.content
