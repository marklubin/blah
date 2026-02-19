"""Tests for HackerNewsAdapter (mocked httpx client)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.hackernews import HackerNewsAdapter


@pytest.fixture
def adapter():
    """Create an adapter (no auth needed)."""
    a = HackerNewsAdapter()
    a.authenticate()
    return a


def _firebase_item(
    id=12345,
    type="story",
    title="Show HN: Something Cool",
    text="",
    by="pg",
    score=42,
    descendants=5,
    time=1700000000,
    url="https://example.com/article",
    kids=None,
    deleted=False,
    dead=False,
):
    """Create a mock Firebase HN item dict."""
    item = {
        "id": id,
        "type": type,
        "title": title,
        "text": text,
        "by": by,
        "score": score,
        "descendants": descendants,
        "time": time,
        "url": url,
    }
    if kids is not None:
        item["kids"] = kids
    if deleted:
        item["deleted"] = True
    if dead:
        item["dead"] = True
    return item


def _firebase_comment(
    id=67890,
    by="commenter",
    text="Great post!",
    time=1700001000,
    parent=12345,
):
    """Create a mock Firebase HN comment dict."""
    return {
        "id": id,
        "type": "comment",
        "by": by,
        "text": text,
        "time": time,
        "parent": parent,
    }


def _algolia_hit(
    objectID="12345",
    title="Show HN: Something Cool",
    author="pg",
    points=42,
    num_comments=5,
    url="https://example.com/article",
    created_at="2023-11-14T22:13:20.000Z",
):
    """Create a mock Algolia search hit."""
    return {
        "objectID": objectID,
        "title": title,
        "author": author,
        "points": points,
        "num_comments": num_comments,
        "url": url,
        "created_at": created_at,
    }


class TestItemToDict:
    def test_story(self):
        item = _firebase_item()
        result = HackerNewsAdapter._item_to_dict(item)

        assert result["uri"] == "hn_12345"
        assert result["external_id"] == "hn_12345"
        assert result["url"] == "https://news.ycombinator.com/item?id=12345"
        assert result["author"] == {"handle": "pg", "display_name": "pg"}
        assert result["text"] == "Show HN: Something Cool"
        assert result["like_count"] == 42
        assert result["reply_count"] == 5
        assert result["title"] == "Show HN: Something Cool"
        assert result["hn_url"] == "https://example.com/article"

    def test_self_post(self):
        """Story without external URL should not have hn_url."""
        item = _firebase_item(url=None, text="Ask HN: What do you think?")
        result = HackerNewsAdapter._item_to_dict(item)

        assert "hn_url" not in result
        assert "Ask HN: What do you think?" in result["text"]

    def test_story_with_body(self):
        """Text should combine title and body."""
        item = _firebase_item(title="Ask HN: Question", text="Details here")
        result = HackerNewsAdapter._item_to_dict(item)

        assert result["text"] == "Ask HN: Question\nDetails here"

    def test_created_at_is_iso_format(self):
        item = _firebase_item(time=1700000000)
        result = HackerNewsAdapter._item_to_dict(item)
        assert "2023-11-14" in result["created_at"]

    def test_comment_type(self):
        """Comments don't get title or hn_url."""
        item = _firebase_comment()
        result = HackerNewsAdapter._item_to_dict(item)

        assert result["uri"] == "hn_67890"
        assert result["text"] == "Great post!"
        assert "title" not in result
        assert "hn_url" not in result


class TestAlgoliaHitToDict:
    def test_basic(self):
        hit = _algolia_hit()
        result = HackerNewsAdapter._algolia_hit_to_dict(hit)

        assert result["uri"] == "hn_12345"
        assert result["external_id"] == "hn_12345"
        assert result["author"] == {"handle": "pg", "display_name": "pg"}
        assert result["text"] == "Show HN: Something Cool"
        assert result["like_count"] == 42
        assert result["reply_count"] == 5
        assert result["title"] == "Show HN: Something Cool"
        assert result["hn_url"] == "https://example.com/article"

    def test_no_url(self):
        hit = _algolia_hit(url=None)
        result = HackerNewsAdapter._algolia_hit_to_dict(hit)
        assert "hn_url" not in result


class TestHackerNewsAdapter:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "hackernews"

    def test_authenticate_is_noop(self):
        a = HackerNewsAdapter()
        a.authenticate()  # Should not raise

    def test_post_raises(self, adapter):
        from blah.adapters.base import PostContent

        with pytest.raises(NotImplementedError):
            adapter.post(PostContent(text="hello"))

    def test_delete_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.delete_post("hn_12345")

    def test_follow_returns_false(self, adapter):
        assert adapter.follow("pg") is False


class TestGetPost:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _firebase_item(id=99)
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post("hn_99")

        assert result is not None
        assert result["external_id"] == "hn_99"
        mock_client.get.assert_called_once()
        assert "item/99.json" in mock_client.get.call_args[0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_without_prefix(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _firebase_item(id=99)
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post("99")
        assert result is not None
        assert result["external_id"] == "hn_99"

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = None
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post("hn_999999")
        assert result is None

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post("hn_99")
        assert result is None


class TestGetTimeline:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()

        # First call: topstories, second call: individual item
        mock_stories_resp = MagicMock()
        mock_stories_resp.json.return_value = [100, 200]

        mock_item_resp_1 = MagicMock()
        mock_item_resp_1.json.return_value = _firebase_item(id=100, title="Story 1")
        mock_item_resp_2 = MagicMock()
        mock_item_resp_2.json.return_value = _firebase_item(id=200, title="Story 2")

        mock_client.get.side_effect = [mock_stories_resp, mock_item_resp_1, mock_item_resp_2]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_timeline(limit=2)

        assert len(result["items"]) == 2
        assert result["items"][0]["external_id"] == "hn_100"
        assert result["items"][1]["external_id"] == "hn_200"
        assert result["cursor"] is None

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_timeline()
        assert result == {"items": [], "cursor": None}


class TestGetAuthorFeed:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()

        mock_user_resp = MagicMock()
        mock_user_resp.json.return_value = {
            "id": "pg",
            "submitted": [100, 200],
        }

        mock_item_resp_1 = MagicMock()
        mock_item_resp_1.json.return_value = _firebase_item(id=100)
        mock_item_resp_2 = MagicMock()
        mock_item_resp_2.json.return_value = _firebase_item(id=200)

        mock_client.get.side_effect = [mock_user_resp, mock_item_resp_1, mock_item_resp_2]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_author_feed("pg", limit=10)

        assert len(result["items"]) == 2
        assert result["cursor"] is None

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_user_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = None
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_author_feed("nobody")
        assert result == {"items": [], "cursor": None}

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("connection error")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_author_feed("pg")
        assert result == {"items": [], "cursor": None}


class TestSearchPosts:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "hits": [_algolia_hit(objectID="111"), _algolia_hit(objectID="222")],
        }
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        results = adapter.search_posts("python", limit=10)

        assert len(results) == 2
        assert results[0]["external_id"] == "hn_111"
        assert results[1]["external_id"] == "hn_222"

        # Check Algolia was called with correct params
        call_args = mock_client.get.call_args
        assert "search" in call_args[0][0]
        assert call_args[1]["params"]["query"] == "python"
        assert call_args[1]["params"]["hitsPerPage"] == 10

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_no_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hits": []}
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        results = adapter.search_posts("xyznonexistent")
        assert results == []

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        results = adapter.search_posts("python")
        assert results == []


class TestGetProfile:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": "pg",
            "about": "Lisp hacker",
            "karma": 155555,
            "created": 1160418111,
            "submitted": list(range(100)),
        }
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_profile("pg")

        assert result is not None
        assert result["handle"] == "pg"
        assert result["display_name"] == "pg"
        assert result["description"] == "Lisp hacker"
        assert result["karma"] == 155555
        assert result["posts_count"] == 100

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = None
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_profile("nobody")
        assert result is None

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("error")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_profile("pg")
        assert result is None


class TestGetPostThread:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_basic(self, mock_client_cls):
        mock_client = MagicMock()

        story = _firebase_item(id=100, kids=[201, 202])
        comment1 = _firebase_comment(id=201, text="First comment")
        comment2 = _firebase_comment(id=202, text="Second comment")

        mock_story_resp = MagicMock()
        mock_story_resp.json.return_value = story
        mock_c1_resp = MagicMock()
        mock_c1_resp.json.return_value = comment1
        mock_c2_resp = MagicMock()
        mock_c2_resp.json.return_value = comment2

        mock_client.get.side_effect = [mock_story_resp, mock_c1_resp, mock_c2_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post_thread("hn_100", depth=5)

        assert result is not None
        assert result["post"]["external_id"] == "hn_100"
        assert result["parents"] == []
        assert len(result["replies"]) == 2
        assert result["replies"][0]["external_id"] == "hn_201"

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_strips_prefix(self, mock_client_cls):
        mock_client = MagicMock()

        story = _firebase_item(id=100)
        mock_resp = MagicMock()
        mock_resp.json.return_value = story
        mock_client.get.return_value = mock_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        adapter.get_post_thread("hn_100")

        assert "item/100.json" in mock_client.get.call_args[0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_skips_deleted_comments(self, mock_client_cls):
        mock_client = MagicMock()

        story = _firebase_item(id=100, kids=[201])
        deleted_comment = _firebase_comment(id=201)
        deleted_comment["deleted"] = True

        mock_story_resp = MagicMock()
        mock_story_resp.json.return_value = story
        mock_c_resp = MagicMock()
        mock_c_resp.json.return_value = deleted_comment

        mock_client.get.side_effect = [mock_story_resp, mock_c_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post_thread("hn_100")
        assert result is not None
        assert len(result["replies"]) == 0

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_post_thread("hn_100")
        assert result is None


class TestGetFrontpage:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_top_stories(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = [100]
        mock_item_resp = MagicMock()
        mock_item_resp.json.return_value = _firebase_item(id=100)

        mock_client.get.side_effect = [mock_ids_resp, mock_item_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_frontpage(sort="top", limit=1)

        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "hn_100"
        # Verify correct endpoint was called
        assert "topstories.json" in mock_client.get.call_args_list[0][0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_new_stories(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = [200]
        mock_item_resp = MagicMock()
        mock_item_resp.json.return_value = _firebase_item(id=200)

        mock_client.get.side_effect = [mock_ids_resp, mock_item_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_frontpage(sort="new", limit=1)

        assert len(result["items"]) == 1
        assert "newstories.json" in mock_client.get.call_args_list[0][0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_show_hn(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = []
        mock_client.get.return_value = mock_ids_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_frontpage(sort="show")

        assert result == {"items": [], "cursor": None}
        assert "showstories.json" in mock_client.get.call_args[0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_unknown_sort_defaults_to_top(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = []
        mock_client.get.return_value = mock_ids_resp

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        adapter.get_frontpage(sort="nonexistent")

        assert "topstories.json" in mock_client.get.call_args[0][0]

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_api_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_frontpage()
        assert result == {"items": [], "cursor": None}


class TestSkipsDeletedAndDead:
    @patch("blah.adapters.hackernews.httpx.Client")
    def test_deleted_items_excluded(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = [100, 200]

        item1 = _firebase_item(id=100)
        item2 = _firebase_item(id=200)
        item2["deleted"] = True

        mock_item1_resp = MagicMock()
        mock_item1_resp.json.return_value = item1
        mock_item2_resp = MagicMock()
        mock_item2_resp.json.return_value = item2

        mock_client.get.side_effect = [mock_ids_resp, mock_item1_resp, mock_item2_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_timeline(limit=2)
        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "hn_100"

    @patch("blah.adapters.hackernews.httpx.Client")
    def test_dead_items_excluded(self, mock_client_cls):
        mock_client = MagicMock()

        mock_ids_resp = MagicMock()
        mock_ids_resp.json.return_value = [100]

        item = _firebase_item(id=100)
        item["dead"] = True

        mock_item_resp = MagicMock()
        mock_item_resp.json.return_value = item

        mock_client.get.side_effect = [mock_ids_resp, mock_item_resp]

        adapter = HackerNewsAdapter()
        adapter._client = mock_client

        result = adapter.get_timeline(limit=1)
        assert len(result["items"]) == 0
