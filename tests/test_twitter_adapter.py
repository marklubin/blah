"""Tests for TwitterAdapter (mocked APIs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.base import PostContent
from blah.adapters.twitter import TwitterAdapter


@pytest.fixture
def adapter():
    """Create an adapter with mock credentials."""
    return TwitterAdapter(
        consumer_key="test_consumer_key",
        consumer_secret="test_consumer_secret",
        access_token="test_access_token",
        access_token_secret="test_access_token_secret",
        twitterapi_io_key="test_twitterapi_io_key",
    )


class TestTwitterAdapter:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "twitter"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_authenticate(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy

        # Mock get_me response
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        adapter.authenticate()

        assert adapter._user_id == "12345"
        assert adapter._username == "testuser"
        mock_tweepy_client_cls.assert_called_once()

    def test_post_before_auth_raises(self, adapter):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            adapter.post(PostContent(text="hello"))

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_post_simple(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy

        # Mock get_me
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        # Mock create_tweet
        mock_response = MagicMock()
        mock_response.data = {"id": "999888777"}
        mock_tweepy.create_tweet.return_value = mock_response

        adapter.authenticate()
        result = adapter.post(PostContent(text="Hello Twitter!"))

        assert result.platform == "twitter"
        assert result.external_id == "999888777"
        assert "testuser/status/999888777" in result.external_url
        mock_tweepy.create_tweet.assert_called_once_with(text="Hello Twitter!")

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_post_reply(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy

        # Mock get_me
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        # Mock create_tweet
        mock_response = MagicMock()
        mock_response.data = {"id": "111222333"}
        mock_tweepy.create_tweet.return_value = mock_response

        adapter.authenticate()
        result = adapter.post(PostContent(
            text="This is a reply",
            reply_to="999888777",
        ))

        assert result.external_id == "111222333"
        mock_tweepy.create_tweet.assert_called_once_with(
            text="This is a reply",
            in_reply_to_tweet_id="999888777",
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_delete_post(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy

        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        adapter.authenticate()
        result = adapter.delete_post("999888777")

        assert result is True
        mock_tweepy.delete_tweet.assert_called_once_with("999888777")

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_get_post_via_twitterapi_io(
        self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter
    ):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        mock_http = MagicMock()
        mock_httpx_client_cls.return_value = mock_http

        # Mock twitterapi.io response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tweets": [{
                "id": "999888777",
                "text": "Hello world",
                "author": {"userName": "someone"},
                "createdAt": "2026-02-04T12:00:00Z",
            }]
        }
        mock_http.get.return_value = mock_resp

        adapter.authenticate()
        result = adapter.get_post("999888777")

        assert result is not None
        assert result["id"] == "999888777"
        assert result["text"] == "Hello world"
        assert result["author"] == "someone"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_get_post_via_tweepy_fallback(self, mock_tweepy_client_cls, mock_httpx_client_cls):
        """When no twitterapi.io key, falls back to tweepy."""
        adapter = TwitterAdapter(
            consumer_key="key",
            consumer_secret="secret",
            access_token="token",
            access_token_secret="token_secret",
            twitterapi_io_key=None,  # No twitterapi.io key
        )

        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        # Mock get_tweet response
        mock_tweet = MagicMock()
        mock_tweet.data.id = 999888777
        mock_tweet.data.text = "Hello via tweepy"
        mock_tweet.data.created_at = None
        mock_tweepy.get_tweet.return_value = mock_tweet

        adapter.authenticate()
        result = adapter.get_post("999888777")

        assert result is not None
        assert result["id"] == "999888777"
        assert result["text"] == "Hello via tweepy"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_get_user_tweets(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        mock_http = MagicMock()
        mock_httpx_client_cls.return_value = mock_http

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tweets": [
                {"id": "1", "text": "Tweet 1", "createdAt": "2026-02-04T12:00:00Z"},
                {"id": "2", "text": "Tweet 2", "createdAt": "2026-02-04T11:00:00Z"},
            ]
        }
        mock_http.get.return_value = mock_resp

        adapter.authenticate()
        tweets = adapter.get_user_tweets("someone", limit=10)

        assert len(tweets) == 2
        assert tweets[0]["text"] == "Tweet 1"
        mock_http.get.assert_called_with(
            "/twitter/user/last_tweets",
            params={"userName": "someone", "limit": 10},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_search_tweets(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        mock_http = MagicMock()
        mock_httpx_client_cls.return_value = mock_http

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tweets": [
                {
                    "id": "1",
                    "text": "Found tweet",
                    "author": {"userName": "author1"},
                    "createdAt": "2026-02-04",
                },
            ]
        }
        mock_http.get.return_value = mock_resp

        adapter.authenticate()
        tweets = adapter.search_tweets("python", limit=5)

        assert len(tweets) == 1
        assert tweets[0]["text"] == "Found tweet"
        assert tweets[0]["author"] == "author1"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.tweepy.Client")
    def test_post_thread(self, mock_tweepy_client_cls, mock_httpx_client_cls, adapter):
        """Test posting a thread (multiple tweets as replies)."""
        mock_tweepy = MagicMock()
        mock_tweepy_client_cls.return_value = mock_tweepy
        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_tweepy.get_me.return_value = mock_me

        # Return different IDs for each tweet
        mock_tweepy.create_tweet.side_effect = [
            MagicMock(data={"id": "100"}),
            MagicMock(data={"id": "101"}),
            MagicMock(data={"id": "102"}),
        ]

        adapter.authenticate()
        results = adapter.post_thread([
            PostContent(text="Thread 1/3"),
            PostContent(text="Thread 2/3"),
            PostContent(text="Thread 3/3"),
        ])

        assert len(results) == 3
        assert results[0].external_id == "100"
        assert results[1].external_id == "101"
        assert results[2].external_id == "102"

        # Check that replies chain correctly
        calls = mock_tweepy.create_tweet.call_args_list
        assert calls[0].kwargs == {"text": "Thread 1/3"}
        assert calls[1].kwargs == {"text": "Thread 2/3", "in_reply_to_tweet_id": "100"}
        assert calls[2].kwargs == {"text": "Thread 3/3", "in_reply_to_tweet_id": "101"}
