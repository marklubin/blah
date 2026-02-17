"""Twitter/X adapter with split read/write APIs.

Reads: twitterapi.io (cheaper, no official API limits)
Writes: Official X API via xdk (OAuth 2.0 PKCE)
"""

from __future__ import annotations

import logging

import httpx
from xdk import Client as XClient

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)


def _get_field(obj, field: str):
    """Get a field from an object that may be a dict or an object with attributes."""
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


# twitterapi.io base URL
TWITTERAPI_IO_BASE = "https://api.twitterapi.io"


class TwitterAdapter(PlatformAdapter):
    """Twitter/X platform adapter.

    Uses twitterapi.io for read operations (cheaper) and
    official X API via xdk for write operations (OAuth 2.0).
    """

    def __init__(
        self,
        # OAuth 2.0 credentials (for writes via xdk)
        client_id: str,
        oauth2_token: dict,
        client_secret: str | None = None,
        # twitterapi.io credentials (for reads)
        twitterapi_io_key: str | None = None,
        # Settings ref for persisting refreshed tokens
        settings=None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._oauth2_token = oauth2_token
        self._twitterapi_io_key = twitterapi_io_key
        self._settings = settings

        self._xdk_client: XClient | None = None
        self._http_client: httpx.Client | None = None
        self._user_id: str | None = None
        self._username: str | None = None

    @property
    def platform_name(self) -> str:
        return "twitter"

    def _ensure_token_fresh(self) -> None:
        """Refresh the OAuth2 token if expired, persisting to settings."""
        if self._xdk_client and self._xdk_client.is_token_expired():
            new_token = self._xdk_client.refresh_token()
            self._oauth2_token = new_token
            if self._settings:
                self._settings.platforms["twitter"].oauth2_token = new_token
                self._settings.save()

    @property
    def xdk_client(self) -> XClient:
        if self._xdk_client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        self._ensure_token_fresh()
        return self._xdk_client

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._http_client

    def authenticate(self) -> None:
        """Authenticate with both APIs."""
        # Official X API client for writes (OAuth 2.0)
        xdk_kwargs = {
            "client_id": self._client_id,
            "token": self._oauth2_token,
            "redirect_uri": "http://127.0.0.1:8888/callback",
            "scope": "tweet.read tweet.write follows.read follows.write users.read offline.access",
        }
        if self._client_secret:
            xdk_kwargs["client_secret"] = self._client_secret
        self._xdk_client = XClient(**xdk_kwargs)

        # Refresh if needed before verifying
        self._ensure_token_fresh()

        # Get authenticated user info
        me = self._xdk_client.users.get_me()
        data = _get_field(me, "data") if me else None
        if data:
            self._user_id = str(_get_field(data, "id"))
            self._username = _get_field(data, "username")
            logger.info("Authenticated to Twitter as @%s", self._username)
        else:
            logger.warning("Could not fetch authenticated user info")

        # HTTP client for twitterapi.io reads
        headers = {}
        if self._twitterapi_io_key:
            headers["x-api-key"] = self._twitterapi_io_key
        self._http_client = httpx.Client(
            base_url=TWITTERAPI_IO_BASE,
            headers=headers,
            timeout=30.0,
        )

    # ── Normalizer ────────────────────────────────────────────────

    @staticmethod
    def _tweet_to_dict(tweet: dict) -> dict:
        """Convert a twitterapi.io tweet object to pipeline-standard format."""
        author_obj = tweet.get("author") or {}
        handle = author_obj.get("userName") or ""
        tweet_id = tweet.get("id") or ""
        url = f"https://x.com/{handle}/status/{tweet_id}" if handle and tweet_id else ""
        return {
            "uri": url,
            "external_id": tweet_id,
            "url": url,
            "author": {
                "handle": handle,
                "display_name": author_obj.get("name") or handle,
            },
            "text": tweet.get("text") or "",
            "created_at": tweet.get("createdAt"),
            "like_count": tweet.get("likeCount", 0),
            "repost_count": tweet.get("retweetCount", 0),
            "reply_count": tweet.get("replyCount", 0),
        }

    # ── Write operations (xdk) ───────────────────────────────────

    def post(self, content: PostContent) -> PostResult:
        """Post a tweet using official X API via xdk."""
        body: dict = {"text": content.text}

        if content.reply_to:
            body["reply"] = {"in_reply_to_tweet_id": content.reply_to}

        response = self.xdk_client.posts.create(body)

        data = _get_field(response, "data")
        if not response or not data:
            raise RuntimeError("Failed to create tweet: no response data")

        tweet_id = str(_get_field(data, "id"))
        url = f"https://x.com/{self._username}/status/{tweet_id}"

        logger.info("Posted tweet %s: %s", tweet_id, url)

        return PostResult(
            external_id=tweet_id,
            external_url=url,
            platform="twitter",
            metadata={"id": tweet_id},
        )

    def delete_post(self, external_id: str) -> bool:
        """Delete a tweet using official X API via xdk."""
        try:
            self.xdk_client.posts.delete(external_id)
            logger.info("Deleted tweet %s", external_id)
            return True
        except Exception as e:
            logger.exception("Failed to delete tweet %s: %s", external_id, e)
            return False

    def follow(self, handle: str) -> bool:
        """Follow a user via official X API (xdk)."""
        try:
            user = self.xdk_client.users.get_by_username(handle)
            user_data = _get_field(user, "data") if user else None
            if not user_data:
                logger.warning("Could not find user @%s", handle)
                return False
            self.xdk_client.users.follow_user(
                self._user_id, {"target_user_id": str(_get_field(user_data, "id"))}
            )
            logger.info("Followed @%s", handle)
            return True
        except Exception as e:
            logger.exception("Failed to follow @%s: %s", handle, e)
            return False

    # ── Read operations (twitterapi.io) ───────────────────────────

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a tweet using twitterapi.io."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot fetch post")
            return None
        return self._get_post_via_twitterapi_io(external_id)

    def _get_post_via_twitterapi_io(self, tweet_id: str) -> dict | None:
        """Fetch tweet via twitterapi.io."""
        try:
            resp = self.http_client.get(
                "/twitter/tweets",
                params={"tweet_ids": tweet_id},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("tweets"):
                return self._tweet_to_dict(data["tweets"][0])
        except Exception:
            logger.exception("Failed to fetch tweet %s via twitterapi.io", tweet_id)
        return None

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch recent tweets by a user via twitterapi.io."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot fetch author feed")
            return {"items": [], "cursor": None}

        try:
            params: dict = {"userName": handle, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            resp = self.http_client.get(
                "/twitter/user/last_tweets",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            items = [self._tweet_to_dict(t) for t in data.get("tweets", [])]
            return {
                "items": items,
                "cursor": data.get("next_cursor"),
            }
        except Exception:
            logger.exception("Failed to fetch author feed for @%s", handle)
            return {"items": [], "cursor": None}

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search tweets via twitterapi.io (pipeline-standard interface)."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot search posts")
            return []

        try:
            resp = self.http_client.get(
                "/twitter/tweet/advanced_search",
                params={"query": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            return [self._tweet_to_dict(t) for t in data.get("tweets", [])]
        except Exception:
            logger.exception("Failed to search posts for: %s", query)
            return []

    def get_timeline(
        self, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch home timeline via xdk (official API)."""
        try:
            kwargs: dict = {"max_results": min(limit, 100)}
            if cursor:
                kwargs["pagination_token"] = cursor

            # xdk get_timeline returns an iterator; we only need the first page
            pages = self.xdk_client.users.get_timeline(
                self._user_id,
                tweet_fields=["created_at", "public_metrics", "author_id"],
                expansions=["author_id"],
                user_fields=["username", "name"],
                **kwargs,
            )
            page = next(pages, None)
            page_data = _get_field(page, "data") if page else None
            if not page_data:
                return {"items": [], "cursor": None}

            # Build author lookup from includes
            authors: dict[str, dict] = {}
            includes = _get_field(page, "includes")
            inc_users = _get_field(includes, "users") if includes else None
            if inc_users:
                for user in inc_users:
                    authors[str(_get_field(user, "id"))] = {
                        "handle": _get_field(user, "username"),
                        "display_name": _get_field(user, "name"),
                    }

            items = []
            for tweet in page_data:
                metrics = _get_field(tweet, "public_metrics") or {}
                if hasattr(metrics, "model_dump"):
                    metrics = metrics.model_dump()
                raw_author_id = _get_field(tweet, "author_id")
                author_id = str(raw_author_id) if raw_author_id else ""
                author = authors.get(author_id, {"handle": "", "display_name": ""})
                handle = author["handle"]
                tweet_id = str(_get_field(tweet, "id"))
                url = f"https://x.com/{handle}/status/{tweet_id}" if handle else ""
                raw_created = _get_field(tweet, "created_at")
                items.append({
                    "uri": url,
                    "external_id": tweet_id,
                    "url": url,
                    "author": author,
                    "text": _get_field(tweet, "text"),
                    "created_at": str(raw_created) if raw_created else None,
                    "like_count": metrics.get("like_count", 0),
                    "repost_count": metrics.get("retweet_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                })

            meta = _get_field(page, "meta")
            next_cursor = _get_field(meta, "next_token") if meta else None
            return {"items": items, "cursor": next_cursor}
        except Exception:
            logger.exception("Failed to fetch home timeline")
            return {"items": [], "cursor": None}

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Fetch a tweet thread via twitterapi.io.

        `uri` is treated as the tweet ID (or a URL — we extract the ID).
        """
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot fetch thread")
            return None

        # Accept tweet URL or bare ID
        tweet_id = uri.rstrip("/").split("/")[-1] if "/" in uri else uri

        try:
            resp = self.http_client.get(
                "/twitter/tweet/thread",
                params={"tweet_id": tweet_id},
            )
            resp.raise_for_status()
            data = resp.json()

            tweets = [self._tweet_to_dict(t) for t in data.get("tweets", [])]
            if not tweets:
                return None

            return {
                "post": tweets[0],
                "parents": [],
                "replies": tweets[1:depth],
            }
        except Exception:
            logger.exception("Failed to fetch thread for %s", tweet_id)
            return None

    def get_profile(self, handle: str) -> dict | None:
        """Fetch a user profile via twitterapi.io."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot fetch profile")
            return None

        try:
            resp = self.http_client.get(
                "/twitter/user/info",
                params={"userName": handle},
            )
            resp.raise_for_status()
            data = resp.json()

            user = data.get("data") or data
            return {
                "did": user.get("id", ""),
                "handle": user.get("userName", handle),
                "display_name": user.get("name", ""),
                "description": user.get("description", ""),
                "followers_count": user.get("followers", 0),
                "follows_count": user.get("following", 0),
                "posts_count": user.get("statusesCount", 0),
            }
        except Exception:
            logger.exception("Failed to fetch profile for @%s", handle)
            return None

    # ── Legacy convenience methods (delegate to pipeline methods) ─

    def get_user_tweets(self, username: str, limit: int = 20) -> list[dict]:
        """Fetch user's recent tweets. Delegates to get_author_feed()."""
        feed = self.get_author_feed(username, limit=limit)
        return feed["items"]

    def search_tweets(self, query: str, limit: int = 20) -> list[dict]:
        """Search tweets. Delegates to search_posts()."""
        return self.search_posts(query, limit=limit)
