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
