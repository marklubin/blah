"""Publishing tools for the Rant Agent."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.agents.tools.base import ToolResult, tool
from blah.config.settings import BlahSettings

logger = logging.getLogger(__name__)


class PublishTools:
    """Tool methods for publishing rants directly from chat."""

    def __init__(self, conn: sqlite3.Connection, settings: BlahSettings, rant_id: str):
        self.conn = conn
        self.settings = settings
        self.rant_id = rant_id
        self._adapters: dict | None = None

    def _get_adapters(self) -> dict:
        """Lazily build and authenticate platform adapters."""
        if self._adapters is not None:
            return self._adapters

        from blah.adapters.bluesky import BlueskyAdapter
        from blah.adapters.twitter import TwitterAdapter

        self._adapters = {}

        # Bluesky
        bsky = self.settings.platforms.get("bluesky")
        if bsky and bsky.enabled and bsky.handle and bsky.app_password:
            logger.info("Initializing Bluesky adapter for %s", bsky.handle)
            adapter = BlueskyAdapter(handle=bsky.handle, app_password=bsky.app_password)
            adapter.authenticate()
            self._adapters["bluesky"] = adapter

        # Twitter/X
        twitter = self.settings.platforms.get("twitter")
        if (
            twitter
            and twitter.enabled
            and twitter.consumer_key
            and twitter.consumer_secret
            and twitter.access_token
            and twitter.access_token_secret
        ):
            logger.info("Initializing Twitter adapter")
            adapter = TwitterAdapter(
                consumer_key=twitter.consumer_key,
                consumer_secret=twitter.consumer_secret,
                access_token=twitter.access_token,
                access_token_secret=twitter.access_token_secret,
                twitterapi_io_key=getattr(twitter, "twitterapi_io_key", None),
            )
            adapter.authenticate()
            self._adapters["twitter"] = adapter

        logger.debug("Initialized %d platform adapters", len(self._adapters))
        return self._adapters

    @tool(
        name="publish_rant",
        description=(
            "Publish all approved pieces for this rant to their platforms. "
            "Call finalize_rant first to mark pieces as approved. "
            "Returns the URLs of published posts."
        ),
        parameters={"type": "object", "properties": {}},
    )
    def publish_rant(self) -> ToolResult:
        from blah.db.repository import PieceRepo, RantRepo
        from blah.services.publishing import PublishService

        rant_repo = RantRepo(self.conn)
        piece_repo = PieceRepo(self.conn)

        rant = rant_repo.get(self.rant_id)
        if rant is None:
            return ToolResult(
                content=json.dumps({"error": "Rant not found"}),
                is_error=True,
            )

        pieces = piece_repo.list_by_rant(self.rant_id)
        approved = [p for p in pieces if p["status"] == "approved"]

        if not approved:
            return ToolResult(
                content=json.dumps({
                    "error": "No approved pieces to publish",
                    "hint": "Call finalize_rant first to approve pieces",
                }),
                is_error=True,
            )

        adapters = self._get_adapters()
        if not adapters:
            return ToolResult(
                content=json.dumps({
                    "error": "No platform adapters configured",
                    "hint": "Configure platform credentials in ~/.blah/config.yaml",
                }),
                is_error=True,
            )

        service = PublishService(self.conn, adapters)
        result = service.publish_rant(self.rant_id)

        published_urls = [
            {"platform": p["platform"], "url": p.get("external_url")}
            for p in result.published
        ]
        failed = [
            {"platform": p["platform"], "error": p.get("error")}
            for p in result.failed
        ]
        skipped = [
            {"platform": p["platform"], "reason": "no adapter"}
            for p in result.skipped
        ]

        # Mark as error if all posts failed
        is_error = len(failed) > 0 and len(published_urls) == 0

        return ToolResult(
            content=json.dumps({
                "published": published_urls,
                "failed": failed,
                "skipped": skipped,
                "summary": result.summary,
            }),
            is_error=is_error,
        )
