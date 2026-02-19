"""Hacker News adapter using the public Firebase and Algolia APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)

FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA_BASE = "https://hn.algolia.com/api/v1"


class HackerNewsAdapter(PlatformAdapter):
    """Hacker News platform adapter (read-only, no auth required)."""

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def platform_name(self) -> str:
        return "hackernews"

    def authenticate(self) -> None:
        """No-op — HN APIs are public."""
        self._client = httpx.Client(timeout=self._timeout)
        logger.info("HackerNews adapter ready (public API, no auth)")

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    # ── Normalizers ──────────────────────────────────────────────

    @staticmethod
    def _item_to_dict(item: dict) -> dict:
        """Convert a Firebase HN item to pipeline-standard format."""
        item_id = item.get("id", "")
        item_type = item.get("type", "story")

        # Build text: title + optional body text
        title = item.get("title", "")
        body = item.get("text", "")
        text = f"{title}\n{body}".strip() if body else title

        created_ts = item.get("time", 0)
        created_at = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
            if created_ts
            else ""
        )

        author = item.get("by", "")

        result = {
            "uri": f"hn_{item_id}",
            "external_id": f"hn_{item_id}",
            "url": f"https://news.ycombinator.com/item?id={item_id}",
            "author": {"handle": author, "display_name": author},
            "text": text,
            "created_at": created_at,
            "like_count": item.get("score", 0),
            "repost_count": 0,
            "reply_count": item.get("descendants", 0),
        }

        if item_type == "story":
            result["title"] = title
            # Linked URL (if it's not a self-post)
            linked_url = item.get("url")
            if linked_url:
                result["hn_url"] = linked_url

        return result

    @staticmethod
    def _algolia_hit_to_dict(hit: dict) -> dict:
        """Convert an Algolia search hit to pipeline-standard format."""
        item_id = hit.get("objectID", "")
        title = hit.get("title") or hit.get("story_title") or ""
        body = hit.get("comment_text") or hit.get("story_text") or ""
        text = f"{title}\n{body}".strip() if body else title

        author = hit.get("author", "")
        created_at = hit.get("created_at", "")

        result = {
            "uri": f"hn_{item_id}",
            "external_id": f"hn_{item_id}",
            "url": f"https://news.ycombinator.com/item?id={item_id}",
            "author": {"handle": author, "display_name": author},
            "text": text,
            "created_at": created_at,
            "like_count": hit.get("points") or 0,
            "repost_count": 0,
            "reply_count": hit.get("num_comments") or 0,
        }

        if title:
            result["title"] = title
        linked_url = hit.get("url")
        if linked_url:
            result["hn_url"] = linked_url

        return result

    # ── Firebase helpers ─────────────────────────────────────────

    def _get_item(self, item_id: int | str) -> dict | None:
        """Fetch a single item from the Firebase API."""
        try:
            resp = self.client.get(f"{FIREBASE_BASE}/item/{item_id}.json")
            resp.raise_for_status()
            data = resp.json()
            if data is None:
                return None
            return data
        except Exception:
            logger.exception("Failed to fetch HN item %s", item_id)
            return None

    def _get_story_ids(self, feed: str, limit: int) -> list[int]:
        """Fetch story IDs from a Firebase feed endpoint."""
        try:
            resp = self.client.get(f"{FIREBASE_BASE}/{feed}.json")
            resp.raise_for_status()
            ids = resp.json() or []
            return ids[:limit]
        except Exception:
            logger.exception("Failed to fetch HN %s", feed)
            return []

    def _fetch_items(self, item_ids: list[int]) -> list[dict]:
        """Fetch multiple items by ID, skipping failures."""
        items = []
        for item_id in item_ids:
            item = self._get_item(item_id)
            if item and not item.get("deleted") and not item.get("dead"):
                items.append(self._item_to_dict(item))
        return items

    # ── Read operations ──────────────────────────────────────────

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a single item by its ID."""
        try:
            raw_id = external_id
            if raw_id.startswith("hn_"):
                raw_id = raw_id[3:]
            item = self._get_item(raw_id)
            if not item:
                return None
            return self._item_to_dict(item)
        except Exception:
            logger.exception("Failed to fetch post %s", external_id)
            return None

    def get_timeline(
        self, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch top stories (default frontpage)."""
        ids = self._get_story_ids("topstories", limit)
        items = self._fetch_items(ids)
        return {"items": items, "cursor": None}

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch a user's submitted items."""
        try:
            resp = self.client.get(f"{FIREBASE_BASE}/user/{handle}.json")
            resp.raise_for_status()
            user_data = resp.json()
            if not user_data:
                return {"items": [], "cursor": None}

            submitted = user_data.get("submitted", [])[:limit]
            items = self._fetch_items(submitted)
            return {"items": items, "cursor": None}
        except Exception:
            logger.exception("Failed to fetch author feed for %s", handle)
            return {"items": [], "cursor": None}

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search via Algolia."""
        try:
            resp = self.client.get(
                f"{ALGOLIA_BASE}/search",
                params={"query": query, "hitsPerPage": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            return [self._algolia_hit_to_dict(h) for h in hits]
        except Exception:
            logger.exception("Failed to search posts for '%s'", query)
            return []

    def get_profile(self, handle: str) -> dict | None:
        """Fetch a user's profile from Firebase."""
        try:
            resp = self.client.get(f"{FIREBASE_BASE}/user/{handle}.json")
            resp.raise_for_status()
            user_data = resp.json()
            if not user_data:
                return None

            return {
                "handle": user_data.get("id", handle),
                "display_name": user_data.get("id", handle),
                "description": user_data.get("about", ""),
                "followers_count": 0,  # HN doesn't expose this
                "posts_count": len(user_data.get("submitted", [])),
                "karma": user_data.get("karma", 0),
                "created_at": (
                    datetime.fromtimestamp(
                        user_data["created"], tz=timezone.utc
                    ).isoformat()
                    if user_data.get("created")
                    else ""
                ),
            }
        except Exception:
            logger.exception("Failed to get profile for %s", handle)
            return None

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Fetch a story and its top comments."""
        try:
            raw_id = uri
            if raw_id.startswith("hn_"):
                raw_id = raw_id[3:]

            item = self._get_item(raw_id)
            if not item:
                return None

            post = self._item_to_dict(item)

            # Fetch top-level comments
            kid_ids = item.get("kids", [])[:depth]
            replies = []
            for kid_id in kid_ids:
                kid = self._get_item(kid_id)
                if kid and not kid.get("deleted") and not kid.get("dead"):
                    replies.append(self._item_to_dict(kid))

            return {
                "post": post,
                "parents": [],
                "replies": replies,
            }
        except Exception:
            logger.exception("Failed to fetch thread for %s", uri)
            return None

    def get_frontpage(
        self, sort: str = "top", limit: int = 30
    ) -> dict:
        """Fetch stories from a specific HN feed.

        Args:
            sort: Feed type — 'top', 'new', 'best', 'ask', 'show', 'job'
            limit: Max stories to fetch
        """
        feed_map = {
            "top": "topstories",
            "new": "newstories",
            "best": "beststories",
            "ask": "askstories",
            "show": "showstories",
            "job": "jobstories",
        }
        feed = feed_map.get(sort, "topstories")

        try:
            ids = self._get_story_ids(feed, limit)
            items = self._fetch_items(ids)
            return {"items": items, "cursor": None}
        except Exception:
            logger.exception("Failed to fetch HN %s feed", sort)
            return {"items": [], "cursor": None}

    # ── Write operations (not supported) ─────────────────────────

    def post(self, content: PostContent) -> PostResult:
        """HN has no write API."""
        raise NotImplementedError("Hacker News does not support posting via API")

    def delete_post(self, external_id: str) -> bool:
        """HN has no write API."""
        raise NotImplementedError("Hacker News does not support deleting via API")

    def follow(self, handle: str) -> bool:
        """HN has no follow API."""
        return False
