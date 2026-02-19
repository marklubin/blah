"""Tests for TelegramAdapter (mocked Telethon client)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.base import PostContent
from blah.adapters.telegram import TelegramAdapter


@pytest.fixture
def adapter():
    """Create an adapter with mocked client."""
    a = TelegramAdapter(api_id=12345, api_hash="abc123", session_string="test_session")
    # Inject a mock client so we skip real authentication
    a._client = MagicMock()
    return a


def _mock_message(msg_id=1, text="Hello world", forwards=3, sender_username="alice", sender_id=100):
    """Create a mock Telethon message."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.forwards = forwards
    msg.date = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)

    sender = MagicMock()
    sender.username = sender_username
    sender.id = sender_id
    sender.first_name = sender_username.capitalize()
    msg.sender = sender

    return msg


class TestPlatformName:
    def test_returns_telegram(self, adapter):
        assert adapter.platform_name == "telegram"


class TestWriteOperations:
    def test_post_raises(self, adapter):
        with pytest.raises(NotImplementedError, match="read-only"):
            adapter.post(PostContent(text="hello"))

    def test_delete_post_raises(self, adapter):
        with pytest.raises(NotImplementedError, match="read-only"):
            adapter.delete_post("tg_chan_1")

    def test_follow_returns_false(self, adapter):
        assert adapter.follow("somechannel") is False


class TestAuthenticate:
    @patch("blah.adapters.telegram.StringSession")
    @patch("blah.adapters.telegram.TelegramClient")
    def test_successful_auth(self, mock_tg_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client.is_user_authorized.return_value = True
        me = MagicMock()
        me.username = "testuser"
        me.id = 12345
        mock_client.get_me.return_value = me
        mock_tg_cls.return_value = mock_client

        a = TelegramAdapter(api_id=1, api_hash="hash", session_string="sess")
        a.authenticate()

        mock_client.connect.assert_called_once()
        assert a._client is mock_client

    @patch("blah.adapters.telegram.StringSession")
    @patch("blah.adapters.telegram.TelegramClient")
    def test_unauthorized_raises(self, mock_tg_cls, mock_session_cls):
        mock_client = MagicMock()
        mock_client.is_user_authorized.return_value = False
        mock_tg_cls.return_value = mock_client

        a = TelegramAdapter(api_id=1, api_hash="hash", session_string="sess")
        with pytest.raises(RuntimeError, match="not authorized"):
            a.authenticate()


class TestClientProperty:
    def test_raises_when_not_authenticated(self):
        a = TelegramAdapter(api_id=1, api_hash="hash", session_string="sess")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            _ = a.client

    def test_returns_client_when_authenticated(self, adapter):
        client = adapter.client
        assert client is adapter._client


class TestGetChannelMessages:
    def test_returns_normalized_messages(self, adapter):
        msg1 = _mock_message(msg_id=10, text="First post", sender_username="alice")
        msg2 = _mock_message(msg_id=11, text="Second post", sender_username="bob")
        adapter._client.get_messages.return_value = [msg1, msg2]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_channel_messages("testchannel", limit=50)

        assert len(result) == 2
        assert result[0]["external_id"] == "tg_testchannel_10"
        assert result[0]["text"] == "First post"
        assert result[0]["url"] == "https://t.me/testchannel/10"
        assert result[0]["author"]["handle"] == "alice"
        assert result[0]["repost_count"] == 3
        assert result[1]["external_id"] == "tg_testchannel_11"

    def test_skips_messages_without_text(self, adapter):
        msg_with_text = _mock_message(msg_id=10, text="Has text")
        msg_no_text = _mock_message(msg_id=11, text=None)
        adapter._client.get_messages.return_value = [msg_with_text, msg_no_text]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_channel_messages("testchannel")

        assert len(result) == 1
        assert result[0]["external_id"] == "tg_testchannel_10"

    def test_handles_sender_without_username(self, adapter):
        msg = _mock_message(msg_id=10, text="Post")
        msg.sender.username = None
        msg.sender.id = 999
        msg.sender.first_name = "NoUsername"
        adapter._client.get_messages.return_value = [msg]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_channel_messages("testchannel")

        assert len(result) == 1
        assert result[0]["author"]["handle"] == "999"
        assert result[0]["author"]["display_name"] == "NoUsername"

    def test_handles_no_sender(self, adapter):
        msg = _mock_message(msg_id=10, text="Channel post")
        msg.sender = None
        adapter._client.get_messages.return_value = [msg]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_channel_messages("testchannel")

        assert len(result) == 1
        assert result[0]["author"]["handle"] == "testchannel"
        assert result[0]["author"]["display_name"] == "testchannel"

    def test_swallows_extra_kwargs(self, adapter):
        """Pipeline passes guild_id, channel_name etc. — adapter must accept them."""
        adapter._client.get_messages.return_value = []
        adapter._client.get_entity.return_value = MagicMock()

        # Should not raise
        result = adapter.get_channel_messages(
            "testchannel", limit=10, guild_id="123", channel_name="general"
        )
        assert result == []

    def test_error_returns_empty(self, adapter):
        adapter._client.get_entity.side_effect = Exception("channel not found")

        result = adapter.get_channel_messages("badchannel")
        assert result == []


class TestGetPost:
    def test_valid_external_id(self, adapter):
        msg = _mock_message(msg_id=42, text="Found it")
        adapter._client.get_messages.return_value = [msg]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_post("tg_testchannel_42")

        assert result is not None
        assert result["external_id"] == "tg_testchannel_42"
        assert result["text"] == "Found it"
        assert result["url"] == "https://t.me/testchannel/42"

    def test_invalid_format_returns_none(self, adapter):
        result = adapter.get_post("bad_format")
        assert result is None

    def test_wrong_prefix_returns_none(self, adapter):
        result = adapter.get_post("xx_channel_123")
        assert result is None

    def test_message_not_found(self, adapter):
        adapter._client.get_messages.return_value = [None]
        adapter._client.get_entity.return_value = MagicMock()

        result = adapter.get_post("tg_testchannel_999")
        assert result is None

    def test_error_returns_none(self, adapter):
        adapter._client.get_entity.side_effect = Exception("fail")

        result = adapter.get_post("tg_testchannel_42")
        assert result is None


class TestSearchPosts:
    def test_returns_empty(self, adapter):
        result = adapter.search_posts("test query")
        assert result == []
