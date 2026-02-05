"""Twitter/X adapter with split read/write APIs.

Reads: twitterapi.io (cheaper, no official API limits)
Writes: Official X API via tweepy (required for posting)
"""

from __future__ import annotations

import logging

import httpx
import tweepy

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)

# twitterapi.io base URL
TWITTERAPI_IO_BASE = "https://api.twitterapi.io"


class TwitterAdapter(PlatformAdapter):
    """Twitter/X platform adapter.

    Uses twitterapi.io for read operations (cheaper) and
    official X API via tweepy for write operations.
    """

    def __init__(
        self,
        # Official X API credentials (for writes)
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        # twitterapi.io credentials (for reads)
        twitterapi_io_key: str | None = None,
    ):
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token = access_token
        self._access_token_secret = access_token_secret
        self._twitterapi_io_key = twitterapi_io_key

        self._tweepy_client: tweepy.Client | None = None
        self._http_client: httpx.Client | None = None
        self._user_id: str | None = None
        self._username: str | None = None

    @property
    def platform_name(self) -> str:
        return "twitter"

    def authenticate(self) -> None:
        """Authenticate with both APIs."""
        # Official X API client for writes
        self._tweepy_client = tweepy.Client(
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret,
            access_token=self._access_token,
            access_token_secret=self._access_token_secret,
        )

        # Get authenticated user info
        me = self._tweepy_client.get_me()
        if me and me.data:
            self._user_id = me.data.id
            self._username = me.data.username
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

    @property
    def tweepy_client(self) -> tweepy.Client:
        if self._tweepy_client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._tweepy_client

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._http_client

    def post(self, content: PostContent) -> PostResult:
        """Post a tweet using official X API."""
        kwargs: dict = {"text": content.text}

        if content.reply_to:
            kwargs["in_reply_to_tweet_id"] = content.reply_to

        response = self.tweepy_client.create_tweet(**kwargs)

        if not response or not response.data:
            raise RuntimeError("Failed to create tweet: no response data")

        tweet_id = response.data["id"]
        url = f"https://x.com/{self._username}/status/{tweet_id}"

        logger.info("Posted tweet %s: %s", tweet_id, url)

        return PostResult(
            external_id=str(tweet_id),
            external_url=url,
            platform="twitter",
            metadata={"id": tweet_id},
        )

    def delete_post(self, external_id: str) -> bool:
        """Delete a tweet using official X API."""
        try:
            self.tweepy_client.delete_tweet(external_id)
            logger.info("Deleted tweet %s", external_id)
            return True
        except tweepy.TweepyException as e:
            logger.exception("Failed to delete tweet %s: %s", external_id, e)
            return False

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a tweet using twitterapi.io (cheaper reads)."""
        if self._twitterapi_io_key:
            return self._get_post_via_twitterapi_io(external_id)
        else:
            return self._get_post_via_tweepy(external_id)

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
                tweet = data["tweets"][0]
                return {
                    "id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "author": tweet.get("author", {}).get("userName"),
                    "created_at": tweet.get("createdAt"),
                }
        except Exception:
            logger.exception("Failed to fetch tweet %s via twitterapi.io", tweet_id)
        return None

    def _get_post_via_tweepy(self, tweet_id: str) -> dict | None:
        """Fetch tweet via official API (fallback)."""
        try:
            response = self.tweepy_client.get_tweet(
                tweet_id,
                expansions=["author_id"],
                tweet_fields=["created_at", "text"],
            )
            if response and response.data:
                created = response.data.created_at
                return {
                    "id": str(response.data.id),
                    "text": response.data.text,
                    "created_at": str(created) if created else None,
                }
        except Exception:
            logger.exception("Failed to fetch tweet %s via tweepy", tweet_id)
        return None

    def get_user_tweets(self, username: str, limit: int = 20) -> list[dict]:
        """Fetch user's recent tweets via twitterapi.io."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot fetch user tweets")
            return []

        try:
            resp = self.http_client.get(
                "/twitter/user/last_tweets",
                params={"userName": username, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            tweets = []
            for tweet in data.get("tweets", []):
                tweets.append({
                    "id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "created_at": tweet.get("createdAt"),
                })
            return tweets
        except Exception:
            logger.exception("Failed to fetch tweets for @%s", username)
            return []

    def search_tweets(self, query: str, limit: int = 20) -> list[dict]:
        """Search tweets via twitterapi.io."""
        if not self._twitterapi_io_key:
            logger.warning("twitterapi.io key not configured, cannot search tweets")
            return []

        try:
            resp = self.http_client.get(
                "/twitter/tweet/advanced_search",
                params={"query": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            tweets = []
            for tweet in data.get("tweets", []):
                tweets.append({
                    "id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "author": tweet.get("author", {}).get("userName"),
                    "created_at": tweet.get("createdAt"),
                })
            return tweets
        except Exception:
            logger.exception("Failed to search tweets for: %s", query)
            return []
