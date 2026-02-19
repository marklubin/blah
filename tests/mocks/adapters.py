"""Mock platform adapters for testing."""

from __future__ import annotations

from blah.adapters.base import PlatformAdapter, PostContent, PostResult


class MockPlatformAdapter(PlatformAdapter):
    """Mock adapter that records calls without hitting any API."""

    def __init__(self, platform: str = "bluesky", fail_on_post: bool = False):
        self._platform = platform
        self._fail_on_post = fail_on_post
        self._authenticated = False
        self.should_fail = False  # When True, feed-fetching methods raise
        self.posts: list[PostContent] = []
        self.deleted: list[str] = []
        self.followed: list[str] = []
        self._post_counter = 0

        # Configurable mock data for feed fetching
        self.timeline_items: list[dict] = []
        self.author_feeds: dict[str, list[dict]] = {}
        self.profiles: dict[str, dict] = {}
        self.threads: dict[str, dict] = {}
        self.search_results: list[dict] = []
        self.subreddit_feeds: dict[str, list[dict]] = {}
        self.frontpage_feeds: dict[str, list[dict]] = {}

    @property
    def platform_name(self) -> str:
        return self._platform

    def authenticate(self) -> None:
        self._authenticated = True

    def post(self, content: PostContent) -> PostResult:
        if self._fail_on_post:
            raise RuntimeError("Mock post failure")

        self._post_counter += 1
        ext_id = f"mock://{self._platform}/{self._post_counter}"
        ext_url = f"https://{self._platform}.example.com/post/{self._post_counter}"
        self.posts.append(content)

        return PostResult(
            external_id=ext_id,
            external_url=ext_url,
            platform=self._platform,
        )

    def delete_post(self, external_id: str) -> bool:
        self.deleted.append(external_id)
        return True

    def get_post(self, external_id: str) -> dict | None:
        return {
            "id": external_id,
            "text": "mock post",
            "like_count": 10,
            "repost_count": 3,
            "reply_count": 5,
        }

    # Feed fetching methods (for Radar)

    def get_timeline(self, limit: int = 50, cursor: str | None = None) -> dict:
        """Return mock timeline items."""
        return {
            "items": self.timeline_items[:limit],
            "cursor": "mock_cursor" if self.timeline_items else None,
        }

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Return mock author feed."""
        if self.should_fail:
            raise ConnectionError("Mock connection failure")
        items = self.author_feeds.get(handle, [])
        return {
            "items": items[:limit],
            "cursor": "mock_cursor" if items else None,
        }

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Return mock thread."""
        return self.threads.get(uri, {
            "post": {"text": "mock post", "author": {"handle": "mock"}},
            "parents": [],
            "replies": [],
        })

    def follow(self, handle: str) -> bool:
        """Mock follow - records the handle."""
        self.followed.append(handle)
        return True

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Return mock search results."""
        return self.search_results[:limit]

    def get_profile(self, handle: str) -> dict | None:
        """Return mock profile."""
        return self.profiles.get(handle, {
            "handle": handle,
            "display_name": f"Mock {handle}",
            "description": "Mock profile",
            "followers_count": 100,
        })

    def get_subreddit_feed(
        self, name: str, sort: str = "hot", limit: int = 30
    ) -> dict:
        """Return mock subreddit feed."""
        items = self.subreddit_feeds.get(name, [])
        return {
            "items": items[:limit],
            "cursor": None,
        }

    def get_frontpage(
        self, sort: str = "top", limit: int = 30
    ) -> dict:
        """Return mock frontpage feed."""
        items = self.frontpage_feeds.get(sort, [])
        return {
            "items": items[:limit],
            "cursor": None,
        }
