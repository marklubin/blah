"""Tests for DiscordAdapter (proxy to MCP router)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from blah.adapters.base import PostContent
from blah.adapters.discord import DiscordAdapter


@pytest.fixture
def adapter():
    """Create an adapter pointing at a fake router."""
    return DiscordAdapter(router_url="http://127.0.0.1:8080")


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestAuthenticate:
    def test_successful_auth(self, adapter):
        """Validates token via router and stores username."""
        mock_resp = _mock_response({"status": "ok", "username": "marklubin", "user_id": "12345"})

        with patch.object(adapter._client, "get", return_value=mock_resp):
            adapter.authenticate()

        assert adapter._username == "marklubin"
        assert adapter._user_id == "12345"

    def test_router_returns_error(self, adapter):
        """Raises on error response from router."""
        mock_resp = _mock_response({"error": "No Discord token configured"})

        with patch.object(adapter._client, "get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Discord auth failed"):
                adapter.authenticate()

    def test_router_unreachable(self, adapter):
        """Raises on connection error."""
        with patch.object(adapter._client, "get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(httpx.ConnectError):
                adapter.authenticate()


class TestPlatformName:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "discord"


class TestGetGuilds:
    def test_returns_guilds(self, adapter):
        guilds = [
            {"id": "g1", "name": "My Server", "owner": True},
            {"id": "g2", "name": "Other Server", "owner": False},
        ]
        mock_resp = _mock_response({"guilds": guilds})

        with patch.object(adapter._client, "get", return_value=mock_resp):
            result = adapter.get_guilds()

        assert len(result) == 2
        assert result[0] == {"id": "g1", "name": "My Server", "owner": True}

    def test_error_returns_empty(self, adapter):
        with patch.object(adapter._client, "get", side_effect=Exception("fail")):
            result = adapter.get_guilds()
        assert result == []


class TestGetGuildChannels:
    def test_returns_channels(self, adapter):
        channels = [
            {"id": "1", "name": "general", "type": 0, "position": 1, "parent_id": None},
            {"id": "2", "name": "announcements", "type": 5, "position": 0, "parent_id": None},
        ]
        mock_resp = _mock_response({"channels": channels})

        with patch.object(adapter._client, "get", return_value=mock_resp) as mock_get:
            result = adapter.get_guild_channels("guild1")

        assert len(result) == 2
        # Router returns pre-sorted channels
        assert result[0]["name"] == "general"
        mock_get.assert_called_once_with("/guilds/guild1/channels")

    def test_error_returns_empty(self, adapter):
        with patch.object(adapter._client, "get", side_effect=Exception("fail")):
            result = adapter.get_guild_channels("guild1")
        assert result == []


class TestGetChannelMessages:
    def test_returns_normalized_messages(self, adapter):
        messages = [
            {
                "external_id": "discord:guild1/chan1/1",
                "text": "First",
                "uri": "discord:guild1/chan1/1",
                "url": "https://discord.com/channels/guild1/chan1/1",
                "author": {"handle": "alice", "display_name": "Alice"},
                "created_at": "2026-02-17T12:00:00+00:00",
                "like_count": 0,
                "reply_count": 0,
                "channel_name": "",
            },
            {
                "external_id": "discord:guild1/chan1/2",
                "text": "Second",
                "uri": "discord:guild1/chan1/2",
                "url": "https://discord.com/channels/guild1/chan1/2",
                "author": {"handle": "bob", "display_name": "Bob"},
                "created_at": "2026-02-17T12:01:00+00:00",
                "like_count": 0,
                "reply_count": 0,
                "channel_name": "",
            },
        ]
        mock_resp = _mock_response({"messages": messages})

        with patch.object(adapter._client, "get", return_value=mock_resp) as mock_get:
            result = adapter.get_channel_messages("chan1", limit=50, guild_id="guild1")

        assert len(result) == 2
        assert result[0]["external_id"] == "discord:guild1/chan1/1"
        assert result[0]["text"] == "First"
        mock_get.assert_called_once_with(
            "/channels/chan1/messages",
            params={"limit": 50, "guild_id": "guild1", "channel_name": ""},
        )

    def test_error_returns_empty(self, adapter):
        with patch.object(adapter._client, "get", side_effect=Exception("fail")):
            result = adapter.get_channel_messages("chan1")
        assert result == []


class TestGetPost:
    def test_fetch_message(self, adapter):
        msg = {
            "external_id": "discord:guild1/chan1/msg1",
            "text": "Hello",
        }
        mock_resp = _mock_response({"messages": [msg]})

        with patch.object(adapter._client, "get", return_value=mock_resp):
            result = adapter.get_post("discord:guild1/chan1/msg1")

        assert result is not None
        assert result["external_id"] == "discord:guild1/chan1/msg1"

    def test_invalid_format_returns_none(self, adapter):
        result = adapter.get_post("invalid-id")
        assert result is None

    def test_error_returns_none(self, adapter):
        with patch.object(adapter._client, "get", side_effect=Exception("fail")):
            result = adapter.get_post("discord:g/c/m")
        assert result is None


class TestPost:
    def test_send_message(self, adapter):
        mock_resp = _mock_response({"message": {"id": "new_msg_1"}})

        with patch.object(adapter._client, "post", return_value=mock_resp) as mock_post:
            result = adapter.post(PostContent(text="Hello!", reply_to="chan1"))

        assert result.platform == "discord"
        assert "new_msg_1" in result.external_id
        assert "chan1" in result.external_url
        mock_post.assert_called_once_with(
            "/channels/chan1/messages", json={"content": "Hello!"}
        )

    def test_missing_reply_to_raises(self, adapter):
        with pytest.raises(ValueError, match="reply_to"):
            adapter.post(PostContent(text="No channel"))


class TestDeletePost:
    def test_delete_message(self, adapter):
        mock_resp = _mock_response({"success": True})

        with patch.object(adapter._client, "delete", return_value=mock_resp) as mock_del:
            result = adapter.delete_post("discord:guild1/chan1/msg1")

        assert result is True
        mock_del.assert_called_once_with("/channels/chan1/messages/msg1")

    def test_invalid_format(self, adapter):
        result = adapter.delete_post("bad-id")
        assert result is False

    def test_error_returns_false(self, adapter):
        with patch.object(adapter._client, "delete", side_effect=Exception("fail")):
            result = adapter.delete_post("discord:g/c/m")
        assert result is False


class TestSearchPosts:
    def test_returns_empty(self, adapter):
        result = adapter.search_posts("test query")
        assert result == []
