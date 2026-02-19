"""Tests for RedditAdapter (mocked PRAW client)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blah.adapters.base import PostContent
from blah.adapters.reddit import RedditAdapter


@pytest.fixture
def adapter():
    """Create an adapter with mock credentials."""
    return RedditAdapter(
        client_id="test_client_id",
        client_secret="test_client_secret",
        username="test_user",
        password="test_password",
        user_agent="test:v0.1",
    )


def _mock_submission(
    id="abc123",
    title="Test Post",
    selftext="Test body",
    permalink="/r/python/comments/abc123/test_post/",
    author="testauthor",
    score=42,
    num_comments=5,
    created_utc=1700000000.0,
    subreddit="python",
):
    """Create a mock PRAW Submission."""
    sub = MagicMock()
    sub.id = id
    sub.title = title
    sub.selftext = selftext
    sub.permalink = permalink
    sub.author = MagicMock(__str__=lambda self: author)
    sub.score = score
    sub.num_comments = num_comments
    sub.created_utc = created_utc
    sub.subreddit = MagicMock(__str__=lambda self: subreddit)
    return sub


def _mock_comment(
    id="xyz789",
    body="Test comment",
    permalink="/r/python/comments/abc123/test_post/xyz789/",
    author="commenter",
    score=10,
    created_utc=1700001000.0,
    subreddit="python",
    num_replies=0,
):
    """Create a mock PRAW Comment."""
    comment = MagicMock()
    comment.id = id
    comment.body = body
    comment.permalink = permalink
    comment.author = MagicMock(__str__=lambda self: author)
    comment.score = score
    comment.created_utc = created_utc
    comment.subreddit = MagicMock(__str__=lambda self: subreddit)
    comment.replies = [MagicMock() for _ in range(num_replies)]
    return comment


class TestSubmissionToDict:
    def test_full_submission(self):
        sub = _mock_submission()
        result = RedditAdapter._submission_to_dict(sub)

        assert result["uri"] == "t3_abc123"
        assert result["external_id"] == "t3_abc123"
        assert result["url"] == "https://reddit.com/r/python/comments/abc123/test_post/"
        assert result["author"] == {"handle": "testauthor", "display_name": "testauthor"}
        assert result["text"] == "Test body"
        assert result["like_count"] == 42
        assert result["repost_count"] == 0
        assert result["reply_count"] == 5
        assert result["title"] == "Test Post"
        assert result["subreddit"] == "python"

    def test_link_post_uses_title(self):
        """When selftext is empty, text falls back to title."""
        sub = _mock_submission(selftext="", title="Link title")
        result = RedditAdapter._submission_to_dict(sub)
        assert result["text"] == "Link title"

    def test_created_at_is_iso_format(self):
        sub = _mock_submission(created_utc=1700000000.0)
        result = RedditAdapter._submission_to_dict(sub)
        assert "2023-11-14" in result["created_at"]


class TestCommentToDict:
    def test_full_comment(self):
        comment = _mock_comment()
        result = RedditAdapter._comment_to_dict(comment)

        assert result["uri"] == "t1_xyz789"
        assert result["external_id"] == "t1_xyz789"
        assert result["url"] == "https://reddit.com/r/python/comments/abc123/test_post/xyz789/"
        assert result["author"] == {"handle": "commenter", "display_name": "commenter"}
        assert result["text"] == "Test comment"
        assert result["like_count"] == 10
        assert result["repost_count"] == 0
        assert result["subreddit"] == "python"

    def test_comment_with_replies(self):
        comment = _mock_comment(num_replies=3)
        result = RedditAdapter._comment_to_dict(comment)
        assert result["reply_count"] == 3


class TestRedditAdapter:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "reddit"

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_authenticate(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        adapter.authenticate()

        mock_reddit_cls.assert_called_once_with(
            client_id="test_client_id",
            client_secret="test_client_secret",
            username="test_user",
            password="test_password",
            user_agent="test:v0.1",
        )
        assert adapter._reddit is mock_reddit

    def test_post_before_auth_raises(self, adapter):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            adapter.post(PostContent(text="hello"))


class TestGetAuthorFeed:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_basic(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_redditor = MagicMock()
        mock_redditor.submissions.new.return_value = [sub]
        mock_reddit.redditor.return_value = mock_redditor

        adapter.authenticate()
        result = adapter.get_author_feed("testauthor", limit=10)

        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "t3_abc123"
        assert result["cursor"] is None
        mock_reddit.redditor.assert_called_with("testauthor")
        mock_redditor.submissions.new.assert_called_with(limit=10)

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.redditor.side_effect = Exception("not found")

        adapter.authenticate()
        result = adapter.get_author_feed("nobody")

        assert result == {"items": [], "cursor": None}


class TestSearchPosts:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_basic(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_subreddit = MagicMock()
        mock_subreddit.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        results = adapter.search_posts("python asyncio", limit=10)

        assert len(results) == 1
        assert results[0]["external_id"] == "t3_abc123"
        mock_reddit.subreddit.assert_called_with("all")
        mock_subreddit.search.assert_called_with("python asyncio", limit=10)

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.subreddit.side_effect = Exception("timeout")

        adapter.authenticate()
        results = adapter.search_posts("query")

        assert results == []


class TestGetSubredditFeed:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_hot(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_subreddit = MagicMock()
        mock_subreddit.hot.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        result = adapter.get_subreddit_feed("python", sort="hot", limit=10)

        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "t3_abc123"
        assert result["cursor"] is None
        mock_reddit.subreddit.assert_called_with("python")
        mock_subreddit.hot.assert_called_with(limit=10)

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_new_sort(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = []
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        result = adapter.get_subreddit_feed("python", sort="new")

        assert result == {"items": [], "cursor": None}
        mock_subreddit.new.assert_called_with(limit=30)

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.subreddit.side_effect = Exception("forbidden")

        adapter.authenticate()
        result = adapter.get_subreddit_feed("private_sub")

        assert result == {"items": [], "cursor": None}


class TestGetProfile:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_basic(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_redditor = MagicMock()
        mock_redditor.id = "user123"
        mock_redditor.name = "testauthor"
        mock_redditor.link_karma = 1000
        mock_redditor.comment_karma = 500
        mock_redditor.subreddit = {"public_description": "A test user", "subscribers": 50}
        mock_reddit.redditor.return_value = mock_redditor

        adapter.authenticate()
        result = adapter.get_profile("testauthor")

        assert result is not None
        assert result["handle"] == "testauthor"
        assert result["display_name"] == "testauthor"
        assert result["posts_count"] == 1500
        mock_reddit.redditor.assert_called_with("testauthor")

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.redditor.side_effect = Exception("not found")

        adapter.authenticate()
        result = adapter.get_profile("nobody")

        assert result is None


class TestGetPostThread:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_basic(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        comment = _mock_comment()
        mock_comments = MagicMock()
        mock_comments.__iter__ = MagicMock(return_value=iter([comment]))
        mock_comments.__getitem__ = MagicMock(side_effect=lambda s: [comment][s])
        sub.comments = mock_comments
        mock_reddit.submission.return_value = sub

        adapter.authenticate()
        result = adapter.get_post_thread("t3_abc123")

        assert result is not None
        assert result["post"]["external_id"] == "t3_abc123"
        assert result["parents"] == []
        assert len(result["replies"]) == 1
        assert result["replies"][0]["external_id"] == "t1_xyz789"

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_strips_prefix(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_comments = MagicMock()
        mock_comments.__iter__ = MagicMock(return_value=iter([]))
        mock_comments.__getitem__ = MagicMock(side_effect=lambda s: [][s])
        sub.comments = mock_comments
        mock_reddit.submission.return_value = sub

        adapter.authenticate()
        adapter.get_post_thread("t3_abc123")

        mock_reddit.submission.assert_called_with(id="abc123")

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.submission.side_effect = Exception("not found")

        adapter.authenticate()
        result = adapter.get_post_thread("t3_nonexistent")

        assert result is None


class TestGetTimeline:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_basic(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_reddit.front.hot.return_value = [sub]

        adapter.authenticate()
        result = adapter.get_timeline(limit=10)

        assert len(result["items"]) == 1
        assert result["items"][0]["external_id"] == "t3_abc123"
        assert result["cursor"] is None
        mock_reddit.front.hot.assert_called_with(limit=10)

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_api_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.front.hot.side_effect = Exception("timeout")

        adapter.authenticate()
        result = adapter.get_timeline()

        assert result == {"items": [], "cursor": None}


class TestPostSubmission:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_new_post(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_submission = MagicMock()
        mock_submission.id = "new123"
        mock_submission.permalink = "/r/python/comments/new123/my_title/"

        mock_subreddit = MagicMock()
        mock_subreddit.submit.return_value = mock_submission
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        result = adapter.post(PostContent(
            text="My Title\nThis is the body",
            link_card="python",
        ))

        assert result.platform == "reddit"
        assert result.external_id == "t3_new123"
        assert "reddit.com" in result.external_url
        mock_reddit.subreddit.assert_called_with("python")
        mock_subreddit.submit.assert_called_once_with(
            title="My Title", selftext="This is the body"
        )

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_title_only(self, mock_reddit_cls, adapter):
        """When text has no newline, body is empty."""
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_submission = MagicMock()
        mock_submission.id = "new456"
        mock_submission.permalink = "/r/test/comments/new456/title_only/"

        mock_subreddit = MagicMock()
        mock_subreddit.submit.return_value = mock_submission
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        adapter.post(PostContent(text="Title only", link_card="test"))

        mock_subreddit.submit.assert_called_once_with(
            title="Title only", selftext=""
        )


class TestPostComment:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_reply_to_submission(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_comment = MagicMock()
        mock_comment.id = "reply1"
        mock_comment.permalink = "/r/python/comments/abc123/test/reply1/"

        mock_submission = MagicMock()
        mock_submission.reply.return_value = mock_comment
        mock_reddit.submission.return_value = mock_submission

        adapter.authenticate()
        result = adapter.post(PostContent(
            text="Great post!",
            reply_to="t3_abc123",
        ))

        assert result.external_id == "t1_reply1"
        assert result.platform == "reddit"
        mock_reddit.submission.assert_called_with(id="abc123")
        mock_submission.reply.assert_called_once_with("Great post!")

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_reply_to_comment(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_reply = MagicMock()
        mock_reply.id = "reply2"
        mock_reply.permalink = "/r/python/comments/abc123/test/reply2/"

        mock_parent_comment = MagicMock()
        mock_parent_comment.reply.return_value = mock_reply
        mock_reddit.comment.return_value = mock_parent_comment

        adapter.authenticate()
        result = adapter.post(PostContent(
            text="I agree!",
            reply_to="t1_xyz789",
        ))

        assert result.external_id == "t1_reply2"
        mock_reddit.comment.assert_called_with(id="xyz789")
        mock_parent_comment.reply.assert_called_once_with("I agree!")


class TestDeletePost:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_delete_submission(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_submission = MagicMock()
        mock_reddit.submission.return_value = mock_submission

        adapter.authenticate()
        result = adapter.delete_post("t3_abc123")

        assert result is True
        mock_reddit.submission.assert_called_with(id="abc123")
        mock_submission.delete.assert_called_once()

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_delete_comment(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_comment = MagicMock()
        mock_reddit.comment.return_value = mock_comment

        adapter.authenticate()
        result = adapter.delete_post("t1_xyz789")

        assert result is True
        mock_reddit.comment.assert_called_with(id="xyz789")
        mock_comment.delete.assert_called_once()

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_delete_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.submission.side_effect = Exception("forbidden")

        adapter.authenticate()
        result = adapter.delete_post("t3_abc123")

        assert result is False


class TestGetPost:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_get_submission(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        sub = _mock_submission()
        mock_reddit.submission.return_value = sub

        adapter.authenticate()
        result = adapter.get_post("t3_abc123")

        assert result is not None
        assert result["external_id"] == "t3_abc123"
        assert result["text"] == "Test body"
        mock_reddit.submission.assert_called_with(id="abc123")

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_get_comment(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        comment = _mock_comment()
        mock_reddit.comment.return_value = comment

        adapter.authenticate()
        result = adapter.get_post("t1_xyz789")

        assert result is not None
        assert result["external_id"] == "t1_xyz789"
        assert result["text"] == "Test comment"
        mock_reddit.comment.assert_called_with(id="xyz789")

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_get_post_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.submission.side_effect = Exception("not found")

        adapter.authenticate()
        result = adapter.get_post("t3_nonexistent")

        assert result is None


class TestFollow:
    @patch("blah.adapters.reddit.praw.Reddit")
    def test_subscribe(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit

        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter.authenticate()
        result = adapter.follow("python")

        assert result is True
        mock_reddit.subreddit.assert_called_with("python")
        mock_subreddit.subscribe.assert_called_once()

    @patch("blah.adapters.reddit.praw.Reddit")
    def test_subscribe_error(self, mock_reddit_cls, adapter):
        mock_reddit = MagicMock()
        mock_reddit_cls.return_value = mock_reddit
        mock_reddit.subreddit.side_effect = Exception("not found")

        adapter.authenticate()
        result = adapter.follow("private_sub")

        assert result is False
