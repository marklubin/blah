"""Tests for TwitterAdapter (mocked APIs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.base import PostContent
from blah.adapters.twitter import TwitterAdapter

# ── Fixtures ──────────────────────────────────────────────────

OAUTH2_TOKEN = {
    "access_token": "test_access_token",
    "refresh_token": "test_refresh_token",
    "token_type": "bearer",
    "expires_at": 9999999999,
    "scope": "tweet.read tweet.write",
}


@pytest.fixture
def adapter():
    """Create an adapter with mock credentials."""
    return TwitterAdapter(
        client_id="test_client_id",
        oauth2_token=OAUTH2_TOKEN,
        twitterapi_io_key="test_twitterapi_io_key",
    )


@pytest.fixture
def adapter_no_io_key():
    """Adapter without twitterapi.io key."""
    return TwitterAdapter(
        client_id="test_client_id",
        oauth2_token=OAUTH2_TOKEN,
        twitterapi_io_key=None,
    )


def _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls=None):
    """Shared helper: set up xdk + httpx mocks and authenticate."""
    mock_xdk = MagicMock()
    mock_xdk_client_cls.return_value = mock_xdk

    # Token is not expired
    mock_xdk.is_token_expired.return_value = False

    mock_me = MagicMock()
    mock_me.data.id = "12345"
    mock_me.data.username = "testuser"
    mock_xdk.users.get_me.return_value = mock_me

    mock_http = MagicMock()
    if mock_httpx_client_cls:
        mock_httpx_client_cls.return_value = mock_http

    adapter.authenticate()
    return mock_xdk, mock_http


# ── Sample twitterapi.io tweet payload ────────────────────────

SAMPLE_TWEET = {
    "id": "999888777",
    "text": "Hello world",
    "author": {"userName": "someone", "name": "Some One"},
    "createdAt": "2026-02-04T12:00:00Z",
    "likeCount": 42,
    "retweetCount": 7,
    "replyCount": 3,
}


class TestTweetToDict:
    def test_full_tweet(self):
        result = TwitterAdapter._tweet_to_dict(SAMPLE_TWEET)
        assert result["uri"] == "https://x.com/someone/status/999888777"
        assert result["external_id"] == "999888777"
        assert result["url"] == "https://x.com/someone/status/999888777"
        assert result["author"] == {"handle": "someone", "display_name": "Some One"}
        assert result["text"] == "Hello world"
        assert result["created_at"] == "2026-02-04T12:00:00Z"
        assert result["like_count"] == 42
        assert result["repost_count"] == 7
        assert result["reply_count"] == 3

    def test_missing_author(self):
        tweet = {"id": "1", "text": "no author"}
        result = TwitterAdapter._tweet_to_dict(tweet)
        assert result["author"] == {"handle": "", "display_name": ""}
        assert result["url"] == ""

    def test_missing_metrics_default_zero(self):
        tweet = {"id": "1", "text": "t", "author": {"userName": "u"}}
        result = TwitterAdapter._tweet_to_dict(tweet)
        assert result["like_count"] == 0
        assert result["repost_count"] == 0
        assert result["reply_count"] == 0

    def test_author_display_name_falls_back_to_handle(self):
        tweet = {"id": "1", "text": "t", "author": {"userName": "handle_only"}}
        result = TwitterAdapter._tweet_to_dict(tweet)
        assert result["author"]["display_name"] == "handle_only"


class TestTwitterAdapter:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "twitter"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_authenticate(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        assert adapter._user_id == "12345"
        assert adapter._username == "testuser"
        mock_xdk_client_cls.assert_called_once()

    def test_post_before_auth_raises(self, adapter):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            adapter.post(PostContent(text="hello"))

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_post_simple(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_response = MagicMock()
        mock_response.data.id = "999888777"
        mock_xdk.posts.create.return_value = mock_response

        result = adapter.post(PostContent(text="Hello Twitter!"))

        assert result.platform == "twitter"
        assert result.external_id == "999888777"
        assert "testuser/status/999888777" in result.external_url
        mock_xdk.posts.create.assert_called_once_with({"text": "Hello Twitter!"})

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_post_reply(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_response = MagicMock()
        mock_response.data.id = "111222333"
        mock_xdk.posts.create.return_value = mock_response

        result = adapter.post(PostContent(
            text="This is a reply",
            reply_to="999888777",
        ))

        assert result.external_id == "111222333"
        mock_xdk.posts.create.assert_called_once_with({
            "text": "This is a reply",
            "reply": {"in_reply_to_tweet_id": "999888777"},
        })

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_delete_post(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        result = adapter.delete_post("999888777")

        assert result is True
        mock_xdk.posts.delete.assert_called_once_with("999888777")

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_delete_post_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_xdk.posts.delete.side_effect = Exception("forbidden")

        result = adapter.delete_post("999888777")

        assert result is False

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_get_post_via_twitterapi_io(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter
    ):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET]}
        mock_http.get.return_value = mock_resp

        result = adapter.get_post("999888777")

        assert result is not None
        assert result["external_id"] == "999888777"
        assert result["text"] == "Hello world"
        assert result["author"]["handle"] == "someone"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_get_post_no_io_key_returns_none(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter_no_io_key
    ):
        """When no twitterapi.io key, get_post returns None."""
        _auth(adapter_no_io_key, mock_xdk_client_cls, mock_httpx_client_cls)

        result = adapter_no_io_key.get_post("999888777")

        assert result is None

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_get_user_tweets_delegates(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter
    ):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET]}
        mock_http.get.return_value = mock_resp

        tweets = adapter.get_user_tweets("someone", limit=10)

        assert len(tweets) == 1
        assert tweets[0]["text"] == "Hello world"
        # Should be normalized dict
        assert tweets[0]["external_id"] == "999888777"
        mock_http.get.assert_called_with(
            "/twitter/user/last_tweets",
            params={"userName": "someone", "limit": 10},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_search_tweets_delegates(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter
    ):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET]}
        mock_http.get.return_value = mock_resp

        tweets = adapter.search_tweets("python", limit=5)

        assert len(tweets) == 1
        assert tweets[0]["text"] == "Hello world"
        # Should be normalized dict
        assert tweets[0]["author"]["handle"] == "someone"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_post_thread(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        """Test posting a thread (multiple tweets as replies)."""
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_xdk.posts.create.side_effect = [
            MagicMock(data=MagicMock(id="100")),
            MagicMock(data=MagicMock(id="101")),
            MagicMock(data=MagicMock(id="102")),
        ]

        results = adapter.post_thread([
            PostContent(text="Thread 1/3"),
            PostContent(text="Thread 2/3"),
            PostContent(text="Thread 3/3"),
        ])

        assert len(results) == 3
        assert results[0].external_id == "100"
        assert results[1].external_id == "101"
        assert results[2].external_id == "102"

        calls = mock_xdk.posts.create.call_args_list
        assert calls[0].args[0] == {"text": "Thread 1/3"}
        assert calls[1].args[0] == {
            "text": "Thread 2/3",
            "reply": {"in_reply_to_tweet_id": "100"},
        }
        assert calls[2].args[0] == {
            "text": "Thread 3/3",
            "reply": {"in_reply_to_tweet_id": "101"},
        }

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_token_refresh_on_authenticate(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter
    ):
        """Token refresh is triggered during authenticate() if expired."""
        mock_xdk = MagicMock()
        mock_xdk_client_cls.return_value = mock_xdk

        # Token is expired
        mock_xdk.is_token_expired.return_value = True
        mock_xdk.refresh_token.return_value = {
            "access_token": "refreshed",
            "refresh_token": "new_refresh",
            "expires_at": 9999999999,
        }

        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_xdk.users.get_me.return_value = mock_me

        adapter.authenticate()

        mock_xdk.refresh_token.assert_called()

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_token_refresh_persists(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter
    ):
        """Token refresh persists to settings when settings ref is provided."""
        mock_settings = MagicMock()
        adapter._settings = mock_settings

        mock_xdk = MagicMock()
        mock_xdk_client_cls.return_value = mock_xdk

        # First call: not expired (during authenticate)
        # Second call: expired (during xdk_client property access)
        mock_xdk.is_token_expired.side_effect = [False, True]

        new_token = {
            "access_token": "refreshed",
            "refresh_token": "new_refresh",
            "expires_at": 9999999999,
        }
        mock_xdk.refresh_token.return_value = new_token

        mock_me = MagicMock()
        mock_me.data.id = "12345"
        mock_me.data.username = "testuser"
        mock_xdk.users.get_me.return_value = mock_me

        adapter.authenticate()

        # Access xdk_client property to trigger refresh
        mock_response = MagicMock()
        mock_response.data.id = "999"
        mock_xdk.posts.create.return_value = mock_response
        adapter.post(PostContent(text="test"))

        mock_settings.platforms.__getitem__("twitter").oauth2_token  # noqa: B018
        mock_settings.save.assert_called()


class TestGetAuthorFeed:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_basic(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tweets": [SAMPLE_TWEET],
            "next_cursor": "abc123",
        }
        mock_http.get.return_value = mock_resp

        result = adapter.get_author_feed("someone", limit=10)

        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "999888777"
        assert result["cursor"] == "abc123"
        mock_http.get.assert_called_with(
            "/twitter/user/last_tweets",
            params={"userName": "someone", "limit": 10},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_with_cursor(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [], "next_cursor": None}
        mock_http.get.return_value = mock_resp

        result = adapter.get_author_feed("someone", cursor="page2")

        mock_http.get.assert_called_with(
            "/twitter/user/last_tweets",
            params={"userName": "someone", "limit": 50, "cursor": "page2"},
        )
        assert result["items"] == []
        assert result["cursor"] is None

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_no_io_key(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter_no_io_key
    ):
        _auth(adapter_no_io_key, mock_xdk_client_cls, mock_httpx_client_cls)

        result = adapter_no_io_key.get_author_feed("someone")

        assert result == {"items": [], "cursor": None}

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_api_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_http.get.side_effect = Exception("network error")

        result = adapter.get_author_feed("someone")

        assert result == {"items": [], "cursor": None}


class TestSearchPosts:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_basic(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET]}
        mock_http.get.return_value = mock_resp

        results = adapter.search_posts("python asyncio", limit=10)

        assert len(results) == 1
        assert results[0]["text"] == "Hello world"
        assert results[0]["author"]["handle"] == "someone"
        mock_http.get.assert_called_with(
            "/twitter/tweet/advanced_search",
            params={"query": "python asyncio", "limit": 10},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_no_io_key(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter_no_io_key
    ):
        _auth(adapter_no_io_key, mock_xdk_client_cls, mock_httpx_client_cls)

        results = adapter_no_io_key.search_posts("query")

        assert results == []

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_api_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_http.get.side_effect = Exception("timeout")

        results = adapter.search_posts("query")

        assert results == []


class TestGetTimeline:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_basic(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_user = MagicMock()
        mock_user.id = 111
        mock_user.username = "poster"
        mock_user.name = "The Poster"

        mock_tweet = MagicMock()
        mock_tweet.id = 555
        mock_tweet.text = "Timeline tweet"
        mock_tweet.author_id = 111
        mock_tweet.created_at = "2026-02-04T10:00:00Z"
        mock_tweet.public_metrics = {
            "like_count": 5,
            "retweet_count": 2,
            "reply_count": 1,
        }

        mock_includes = MagicMock()
        mock_includes.users = [mock_user]

        mock_page = MagicMock()
        mock_page.data = [mock_tweet]
        mock_page.includes = mock_includes
        mock_page.meta = MagicMock(next_token="next_page")

        mock_xdk.users.get_timeline.return_value = iter([mock_page])

        result = adapter.get_timeline(limit=10)

        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["text"] == "Timeline tweet"
        assert item["author"] == {"handle": "poster", "display_name": "The Poster"}
        assert item["like_count"] == 5
        assert item["repost_count"] == 2
        assert item["reply_count"] == 1
        assert result["cursor"] == "next_page"

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_empty_response(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_page = MagicMock()
        mock_page.data = None
        mock_xdk.users.get_timeline.return_value = iter([mock_page])

        result = adapter.get_timeline()

        assert result == {"items": [], "cursor": None}

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_api_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_xdk.users.get_timeline.side_effect = Exception("403 Forbidden")

        result = adapter.get_timeline()

        assert result == {"items": [], "cursor": None}


class TestGetPostThread:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_basic(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        reply = {**SAMPLE_TWEET, "id": "999888778", "text": "reply"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET, reply]}
        mock_http.get.return_value = mock_resp

        result = adapter.get_post_thread("999888777")

        assert result is not None
        assert result["post"]["external_id"] == "999888777"
        assert len(result["replies"]) == 1
        assert result["replies"][0]["text"] == "reply"
        assert result["parents"] == []
        mock_http.get.assert_called_with(
            "/twitter/tweet/thread",
            params={"tweet_id": "999888777"},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_from_url(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": [SAMPLE_TWEET]}
        mock_http.get.return_value = mock_resp

        adapter.get_post_thread("https://x.com/someone/status/999888777")

        mock_http.get.assert_called_with(
            "/twitter/tweet/thread",
            params={"tweet_id": "999888777"},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_empty_thread(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tweets": []}
        mock_http.get.return_value = mock_resp

        result = adapter.get_post_thread("999")

        assert result is None

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_no_io_key(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter_no_io_key
    ):
        _auth(adapter_no_io_key, mock_xdk_client_cls, mock_httpx_client_cls)

        result = adapter_no_io_key.get_post_thread("999")

        assert result is None


class TestGetProfile:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_basic(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "id": "12345",
                "userName": "someone",
                "name": "Some One",
                "description": "A person",
                "followers": 1000,
                "following": 500,
                "statusesCount": 5000,
            }
        }
        mock_http.get.return_value = mock_resp

        result = adapter.get_profile("someone")

        assert result is not None
        assert result["did"] == "12345"
        assert result["handle"] == "someone"
        assert result["display_name"] == "Some One"
        assert result["description"] == "A person"
        assert result["followers_count"] == 1000
        assert result["follows_count"] == 500
        assert result["posts_count"] == 5000
        mock_http.get.assert_called_with(
            "/twitter/user/info",
            params={"userName": "someone"},
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_no_io_key(
        self, mock_xdk_client_cls, mock_httpx_client_cls, adapter_no_io_key
    ):
        _auth(adapter_no_io_key, mock_xdk_client_cls, mock_httpx_client_cls)

        result = adapter_no_io_key.get_profile("someone")

        assert result is None

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_api_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        _, mock_http = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_http.get.side_effect = Exception("not found")

        result = adapter.get_profile("nobody")

        assert result is None


class TestFollow:
    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_success(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_user = MagicMock()
        mock_user.data.id = "67890"
        mock_xdk.users.get_by_username.return_value = mock_user

        result = adapter.follow("someone")

        assert result is True
        mock_xdk.users.get_by_username.assert_called_once_with("someone")
        mock_xdk.users.follow_user.assert_called_once_with(
            "12345", {"target_user_id": "67890"}
        )

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_user_not_found(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_user = MagicMock()
        mock_user.data = None
        mock_xdk.users.get_by_username.return_value = mock_user

        result = adapter.follow("nobody")

        assert result is False
        mock_xdk.users.follow_user.assert_not_called()

    @patch("blah.adapters.twitter.httpx.Client")
    @patch("blah.adapters.twitter.XClient")
    def test_api_error(self, mock_xdk_client_cls, mock_httpx_client_cls, adapter):
        mock_xdk, _ = _auth(adapter, mock_xdk_client_cls, mock_httpx_client_cls)

        mock_xdk.users.get_by_username.side_effect = Exception("forbidden")

        result = adapter.follow("someone")

        assert result is False
