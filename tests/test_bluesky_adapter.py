"""Tests for BlueskyAdapter (mocked atproto client)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.base import PostContent
from blah.adapters.bluesky import BlueskyAdapter


@pytest.fixture
def adapter():
    """Create an adapter with mocked atproto client."""
    a = BlueskyAdapter(handle="test.bsky.social", app_password="fake-password")
    return a


def _mock_send_post_response(uri="at://did:plc:abc/app.bsky.feed.post/123", cid="bafyabc"):
    """Create a mock response for send_post."""
    resp = MagicMock()
    resp.uri = uri
    resp.cid = cid
    return resp


def _mock_post_view(uri, cid, text, reply=None):
    """Create a mock post view for get_posts."""
    post = MagicMock()
    post.uri = uri
    post.cid = cid
    post.record = MagicMock()
    post.record.text = text
    post.record.created_at = "2026-02-04T00:00:00Z"
    post.record.reply = reply
    return post


class TestBlueskyAdapter:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "bluesky"

    @patch("blah.adapters.bluesky.Client")
    def test_authenticate(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        adapter.authenticate()

        mock_client.login.assert_called_once_with(
            login="test.bsky.social",
            password="fake-password",
        )

    def test_post_before_auth_raises(self, adapter):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            adapter.post(PostContent(text="hello"))

    @patch("blah.adapters.bluesky.Client")
    def test_post_simple(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.send_post.return_value = _mock_send_post_response()

        adapter.authenticate()
        result = adapter.post(PostContent(text="Hello Bluesky!"))

        assert result.platform == "bluesky"
        assert result.external_id == "at://did:plc:abc/app.bsky.feed.post/123"
        assert "bsky.app/profile/test.bsky.social/post/123" in result.external_url
        mock_client.send_post.assert_called_once_with(
            text="Hello Bluesky!",
            reply_to=None,
        )

    @patch("blah.adapters.bluesky.Client")
    def test_post_reply(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Setup: parent post to reply to
        parent = _mock_post_view(
            uri="at://did:plc:abc/app.bsky.feed.post/parent1",
            cid="bafyparent",
            text="parent post",
        )
        mock_client.get_posts.return_value = MagicMock(posts=[parent])
        mock_client.send_post.return_value = _mock_send_post_response(
            uri="at://did:plc:abc/app.bsky.feed.post/reply1",
        )

        adapter.authenticate()
        result = adapter.post(PostContent(
            text="This is a reply",
            reply_to="at://did:plc:abc/app.bsky.feed.post/parent1",
        ))

        assert result.external_id == "at://did:plc:abc/app.bsky.feed.post/reply1"
        # send_post should have been called with a reply_to
        call_kwargs = mock_client.send_post.call_args
        assert call_kwargs.kwargs["reply_to"] is not None

    @patch("blah.adapters.bluesky.Client")
    def test_delete_post(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.delete_post.return_value = True

        adapter.authenticate()
        result = adapter.delete_post("at://did:plc:abc/app.bsky.feed.post/123")

        assert result is True
        mock_client.delete_post.assert_called_once_with(
            "at://did:plc:abc/app.bsky.feed.post/123"
        )

    @patch("blah.adapters.bluesky.Client")
    def test_get_post(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        post = _mock_post_view(
            uri="at://did:plc:abc/app.bsky.feed.post/123",
            cid="bafyabc",
            text="hello world",
        )
        mock_client.get_posts.return_value = MagicMock(posts=[post])

        adapter.authenticate()
        result = adapter.get_post("at://did:plc:abc/app.bsky.feed.post/123")

        assert result is not None
        assert result["text"] == "hello world"
        assert result["uri"] == "at://did:plc:abc/app.bsky.feed.post/123"

    @patch("blah.adapters.bluesky.Client")
    def test_get_post_not_found(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_posts.return_value = MagicMock(posts=[])

        adapter.authenticate()
        result = adapter.get_post("at://did:plc:abc/app.bsky.feed.post/nonexistent")

        assert result is None

    @patch("blah.adapters.bluesky.Client")
    def test_post_thread(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # First post returns, then second post as reply
        responses = [
            _mock_send_post_response(uri="at://did:plc:abc/app.bsky.feed.post/1", cid="cid1"),
            _mock_send_post_response(uri="at://did:plc:abc/app.bsky.feed.post/2", cid="cid2"),
        ]
        mock_client.send_post.side_effect = responses

        # For the reply reference lookup
        parent = _mock_post_view(
            uri="at://did:plc:abc/app.bsky.feed.post/1",
            cid="cid1",
            text="first post",
        )
        mock_client.get_posts.return_value = MagicMock(posts=[parent])

        adapter.authenticate()
        results = adapter.post_thread([
            PostContent(text="First post"),
            PostContent(text="Second post (reply)"),
        ])

        assert len(results) == 2
        assert results[0].external_id == "at://did:plc:abc/app.bsky.feed.post/1"
        assert results[1].external_id == "at://did:plc:abc/app.bsky.feed.post/2"
