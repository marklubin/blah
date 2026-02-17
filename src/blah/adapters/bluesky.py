"""Bluesky adapter using atproto SDK."""

from __future__ import annotations

import logging

from atproto import Client, models

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)


class BlueskyAdapter(PlatformAdapter):
    """Bluesky platform adapter using AT Protocol."""

    def __init__(self, handle: str, app_password: str):
        self._handle = handle
        self._app_password = app_password
        self._client: Client | None = None

    @property
    def platform_name(self) -> str:
        return "bluesky"

    def authenticate(self) -> None:
        self._client = Client()
        self._client.login(login=self._handle, password=self._app_password)
        logger.info("Authenticated to Bluesky as %s", self._handle)

    @property
    def client(self) -> Client:
        if self._client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._client

    def post(self, content: PostContent) -> PostResult:
        reply_to = None
        if content.reply_to:
            reply_to = self._build_reply_ref(content.reply_to)

        response = self.client.send_post(
            text=content.text,
            reply_to=reply_to,
        )

        rkey = response.uri.split("/")[-1]
        url = f"https://bsky.app/profile/{self._handle}/post/{rkey}"

        return PostResult(
            external_id=response.uri,
            external_url=url,
            platform="bluesky",
            metadata={"cid": response.cid, "uri": response.uri},
        )

    def delete_post(self, external_id: str) -> bool:
        return self.client.delete_post(external_id)

    def get_post(self, external_id: str) -> dict | None:
        try:
            posts = self.client.get_posts(uris=[external_id])
            if posts.posts:
                p = posts.posts[0]
                return {
                    "uri": p.uri,
                    "cid": p.cid,
                    "text": p.record.text,
                    "created_at": str(p.record.created_at) if p.record.created_at else None,
                }
        except Exception:
            logger.exception("Failed to fetch post %s", external_id)
        return None

    def _build_reply_ref(self, parent_uri: str) -> models.AppBskyFeedPost.ReplyRef:
        """Build a reply reference from a parent post URI."""
        posts = self.client.get_posts(uris=[parent_uri])
        if not posts.posts:
            raise ValueError(f"Could not fetch parent post: {parent_uri}")

        parent = posts.posts[0]

        # If the parent is itself a reply, use the original root
        if parent.record.reply:
            root_ref = models.ComAtprotoRepoStrongRef.Main(
                uri=parent.record.reply.root.uri,
                cid=parent.record.reply.root.cid,
            )
        else:
            root_ref = models.ComAtprotoRepoStrongRef.Main(
                uri=parent.uri,
                cid=parent.cid,
            )

        return models.AppBskyFeedPost.ReplyRef(
            parent=models.ComAtprotoRepoStrongRef.Main(
                uri=parent.uri,
                cid=parent.cid,
            ),
            root=root_ref,
        )

    # ─────────────────────────────────────────────────────────────────
    # Feed fetching methods (for Radar)
    # ─────────────────────────────────────────────────────────────────

    def get_timeline(self, limit: int = 50, cursor: str | None = None) -> dict:
        """Fetch the authenticated user's home timeline.

        Returns:
            dict with 'items' (list of post dicts) and 'cursor' for pagination
        """
        try:
            response = self.client.get_timeline(limit=limit, cursor=cursor)
            items = [self._feed_view_to_dict(post) for post in response.feed]
            return {
                "items": items,
                "cursor": response.cursor,
            }
        except Exception:
            logger.exception("Failed to fetch timeline")
            return {"items": [], "cursor": None}

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch posts from a specific author.

        Args:
            handle: Bluesky handle (e.g., 'karpathy.bsky.social')
            limit: Max posts to fetch
            cursor: Pagination cursor

        Returns:
            dict with 'items' and 'cursor'
        """
        try:
            response = self.client.get_author_feed(
                actor=handle, limit=limit, cursor=cursor
            )
            items = [self._feed_view_to_dict(post) for post in response.feed]
            return {
                "items": items,
                "cursor": response.cursor,
            }
        except Exception:
            logger.exception("Failed to fetch author feed for %s", handle)
            return {"items": [], "cursor": None}

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Fetch the full thread context for a post.

        Args:
            uri: Post URI (at://did:plc:.../app.bsky.feed.post/...)
            depth: How deep to fetch replies

        Returns:
            dict with 'post', 'parent' chain, and 'replies'
        """
        try:
            response = self.client.get_post_thread(uri=uri, depth=depth)
            return self._thread_to_dict(response.thread)
        except Exception:
            logger.exception("Failed to fetch thread for %s", uri)
            return None

    def follow(self, handle: str) -> bool:
        """Follow a user by handle.

        Args:
            handle: Bluesky handle to follow

        Returns:
            True if successful
        """
        try:
            # Resolve handle to DID
            profile = self.client.get_profile(actor=handle)
            did = profile.did

            # Create follow record
            self.client.follow(did)
            logger.info("Followed %s (%s)", handle, did)
            return True
        except Exception:
            logger.exception("Failed to follow %s", handle)
            return False

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search for posts matching a query.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of post dicts
        """
        try:
            response = self.client.app.bsky.feed.search_posts(
                params={"q": query, "limit": limit}
            )
            return [self._post_view_to_dict(post) for post in response.posts]
        except Exception:
            logger.exception("Failed to search posts for '%s'", query)
            return []

    def get_profile(self, handle: str) -> dict | None:
        """Get a user's profile information.

        Args:
            handle: Bluesky handle

        Returns:
            Profile dict or None
        """
        try:
            profile = self.client.get_profile(actor=handle)
            return {
                "did": profile.did,
                "handle": profile.handle,
                "display_name": profile.display_name,
                "description": profile.description,
                "followers_count": profile.followers_count,
                "follows_count": profile.follows_count,
                "posts_count": profile.posts_count,
            }
        except Exception:
            logger.exception("Failed to get profile for %s", handle)
            return None

    def _feed_view_to_dict(self, feed_view) -> dict:
        """Convert a FeedViewPost to a simple dict."""
        post = feed_view.post
        return self._post_view_to_dict(post)

    def _post_view_to_dict(self, post) -> dict:
        """Convert a PostView to a simple dict."""
        author = post.author
        record = post.record

        # Extract rkey for URL
        rkey = post.uri.split("/")[-1]
        url = f"https://bsky.app/profile/{author.handle}/post/{rkey}"

        return {
            "uri": post.uri,
            "cid": post.cid,
            "url": url,
            "author": {
                "did": author.did,
                "handle": author.handle,
                "display_name": author.display_name,
            },
            "text": record.text if hasattr(record, "text") else "",
            "created_at": str(record.created_at) if hasattr(record, "created_at") else None,
            "like_count": post.like_count or 0,
            "repost_count": post.repost_count or 0,
            "reply_count": post.reply_count or 0,
        }

    def _thread_to_dict(self, thread) -> dict:
        """Convert a ThreadViewPost to a dict with parent chain and replies."""
        result = {
            "post": self._post_view_to_dict(thread.post) if hasattr(thread, "post") else None,
            "parents": [],
            "replies": [],
        }

        # Walk up parent chain
        if hasattr(thread, "parent") and thread.parent:
            parent = thread.parent
            while parent and hasattr(parent, "post"):
                result["parents"].insert(0, self._post_view_to_dict(parent.post))
                parent = getattr(parent, "parent", None)

        # Collect replies
        if hasattr(thread, "replies") and thread.replies:
            for reply in thread.replies:
                if hasattr(reply, "post"):
                    result["replies"].append(self._post_view_to_dict(reply.post))

        return result
