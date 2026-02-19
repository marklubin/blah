"""Reddit adapter using PRAW."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import praw

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)


class RedditAdapter(PlatformAdapter):
    """Reddit platform adapter using PRAW."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        user_agent: str = "blah:v0.1",
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._user_agent = user_agent
        self._reddit: praw.Reddit | None = None

    @property
    def platform_name(self) -> str:
        return "reddit"

    def authenticate(self) -> None:
        self._reddit = praw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            username=self._username,
            password=self._password,
            user_agent=self._user_agent,
        )
        logger.info("Authenticated to Reddit as %s", self._username)

    @property
    def reddit(self) -> praw.Reddit:
        if self._reddit is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._reddit

    # ── Normalizers ──────────────────────────────────────────────

    @staticmethod
    def _submission_to_dict(submission) -> dict:
        """Convert a PRAW Submission to pipeline-standard format."""
        return {
            "uri": f"t3_{submission.id}",
            "external_id": f"t3_{submission.id}",
            "url": f"https://reddit.com{submission.permalink}",
            "author": {
                "handle": str(submission.author),
                "display_name": str(submission.author),
            },
            "text": submission.selftext or submission.title,
            "created_at": datetime.fromtimestamp(
                submission.created_utc, tz=timezone.utc
            ).isoformat(),
            "like_count": submission.score,
            "repost_count": 0,
            "reply_count": submission.num_comments,
            "title": submission.title,
            "subreddit": str(submission.subreddit),
        }

    @staticmethod
    def _comment_to_dict(comment) -> dict:
        """Convert a PRAW Comment to pipeline-standard format."""
        return {
            "uri": f"t1_{comment.id}",
            "external_id": f"t1_{comment.id}",
            "url": f"https://reddit.com{comment.permalink}",
            "author": {
                "handle": str(comment.author),
                "display_name": str(comment.author),
            },
            "text": comment.body,
            "created_at": datetime.fromtimestamp(
                comment.created_utc, tz=timezone.utc
            ).isoformat(),
            "like_count": comment.score,
            "repost_count": 0,
            "reply_count": len(comment.replies) if hasattr(comment.replies, '__len__') else 0,
            "subreddit": str(comment.subreddit),
        }

    # ── Read operations ──────────────────────────────────────────

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a submission or comment by its full ID (t3_ or t1_ prefix)."""
        try:
            raw_id = external_id
            if raw_id.startswith("t3_"):
                submission = self.reddit.submission(id=raw_id[3:])
                return self._submission_to_dict(submission)
            elif raw_id.startswith("t1_"):
                comment = self.reddit.comment(id=raw_id[3:])
                return self._comment_to_dict(comment)
            else:
                # Assume submission if no prefix
                submission = self.reddit.submission(id=raw_id)
                return self._submission_to_dict(submission)
        except Exception:
            logger.exception("Failed to fetch post %s", external_id)
            return None

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch recent submissions by a Reddit user."""
        try:
            redditor = self.reddit.redditor(handle)
            submissions = redditor.submissions.new(limit=limit)
            items = [self._submission_to_dict(s) for s in submissions]
            return {"items": items, "cursor": None}
        except Exception:
            logger.exception("Failed to fetch author feed for u/%s", handle)
            return {"items": [], "cursor": None}

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search across all subreddits."""
        try:
            results = self.reddit.subreddit("all").search(query, limit=limit)
            return [self._submission_to_dict(s) for s in results]
        except Exception:
            logger.exception("Failed to search posts for '%s'", query)
            return []

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Fetch a submission and its comments."""
        try:
            submission_id = uri
            if submission_id.startswith("t3_"):
                submission_id = submission_id[3:]

            submission = self.reddit.submission(id=submission_id)
            submission.comments.replace_more(limit=0)

            replies = []
            for comment in submission.comments[:depth]:
                replies.append(self._comment_to_dict(comment))

            return {
                "post": self._submission_to_dict(submission),
                "parents": [],
                "replies": replies,
            }
        except Exception:
            logger.exception("Failed to fetch thread for %s", uri)
            return None

    def get_profile(self, handle: str) -> dict | None:
        """Fetch a Reddit user's profile."""
        try:
            redditor = self.reddit.redditor(handle)
            # Access an attribute to trigger the fetch
            _ = redditor.id
            return {
                "handle": redditor.name,
                "display_name": redditor.name,
                "description": getattr(redditor, "subreddit", {}).get("public_description", "") if isinstance(getattr(redditor, "subreddit", None), dict) else "",
                "followers_count": getattr(redditor, "subreddit", {}).get("subscribers", 0) if isinstance(getattr(redditor, "subreddit", None), dict) else 0,
                "posts_count": redditor.link_karma + redditor.comment_karma,
            }
        except Exception:
            logger.exception("Failed to get profile for u/%s", handle)
            return None

    def get_timeline(
        self, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch the user's front page (hot posts)."""
        try:
            posts = self.reddit.front.hot(limit=limit)
            items = [self._submission_to_dict(s) for s in posts]
            return {"items": items, "cursor": None}
        except Exception:
            logger.exception("Failed to fetch front page")
            return {"items": [], "cursor": None}

    def get_subreddit_feed(
        self, name: str, sort: str = "hot", limit: int = 30
    ) -> dict:
        """Fetch posts from a specific subreddit.

        Args:
            name: Subreddit name (without r/ prefix)
            sort: Sort order ('hot', 'new', 'top', 'rising')
            limit: Max posts to fetch
        """
        try:
            subreddit = self.reddit.subreddit(name)
            sort_method = getattr(subreddit, sort, subreddit.hot)
            posts = sort_method(limit=limit)
            items = [self._submission_to_dict(s) for s in posts]
            return {"items": items, "cursor": None}
        except Exception:
            logger.exception("Failed to fetch r/%s feed", name)
            return {"items": [], "cursor": None}

    # ── Write operations ─────────────────────────────────────────

    def post(self, content: PostContent) -> PostResult:
        """Post to Reddit.

        If content.reply_to is set, posts a comment reply.
        Otherwise, submits a new text post. The subreddit is determined
        from content.link_card (used as subreddit name).
        """
        if content.reply_to:
            return self._post_comment(content)
        return self._post_submission(content)

    def _post_submission(self, content: PostContent) -> PostResult:
        """Submit a new text post to a subreddit."""
        subreddit_name = content.link_card or "self"
        subreddit = self.reddit.subreddit(subreddit_name)

        # Use first line as title, rest as body
        lines = content.text.split("\n", 1)
        title = lines[0]
        body = lines[1] if len(lines) > 1 else ""

        submission = subreddit.submit(title=title, selftext=body)

        external_id = f"t3_{submission.id}"
        url = f"https://reddit.com{submission.permalink}"

        logger.info("Posted to r/%s: %s", subreddit_name, url)

        return PostResult(
            external_id=external_id,
            external_url=url,
            platform="reddit",
            metadata={"id": submission.id, "subreddit": subreddit_name},
        )

    def _post_comment(self, content: PostContent) -> PostResult:
        """Post a comment reply."""
        parent_id = content.reply_to
        if parent_id.startswith("t3_"):
            parent = self.reddit.submission(id=parent_id[3:])
        elif parent_id.startswith("t1_"):
            parent = self.reddit.comment(id=parent_id[3:])
        else:
            parent = self.reddit.submission(id=parent_id)

        comment = parent.reply(content.text)

        external_id = f"t1_{comment.id}"
        url = f"https://reddit.com{comment.permalink}"

        logger.info("Posted comment: %s", url)

        return PostResult(
            external_id=external_id,
            external_url=url,
            platform="reddit",
            metadata={"id": comment.id},
        )

    def delete_post(self, external_id: str) -> bool:
        """Delete a submission or comment."""
        try:
            if external_id.startswith("t3_"):
                thing = self.reddit.submission(id=external_id[3:])
            elif external_id.startswith("t1_"):
                thing = self.reddit.comment(id=external_id[3:])
            else:
                thing = self.reddit.submission(id=external_id)

            thing.delete()
            logger.info("Deleted %s", external_id)
            return True
        except Exception:
            logger.exception("Failed to delete %s", external_id)
            return False

    def follow(self, handle: str) -> bool:
        """Subscribe to a subreddit."""
        try:
            subreddit = self.reddit.subreddit(handle)
            subreddit.subscribe()
            logger.info("Subscribed to r/%s", handle)
            return True
        except Exception:
            logger.exception("Failed to subscribe to r/%s", handle)
            return False
