"""Radar pipeline — orchestrates poll → triage → research → report."""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field

import httpx

from blah.adapters.base import PlatformAdapter
from blah.config.settings import BlahSettings
from blah.llm.client import LLMClient
from blah.memory.file_provider import FileMemoryProvider
from blah.db.repository import (
    FeedItemRepo,
    PieceMetricsRepo,
    PieceRepo,
    ReportItemRepo,
    ReportRepo,
    SourceRepo,
)
from blah.services.research import ResearchService
from blah.services.triage import TriageService

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the radar pipeline."""

    # Polling stats
    sources_polled: list[str] = field(default_factory=list)
    items_fetched: int = 0

    # Triage stats
    items_triaged: int = 0
    items_passed: int = 0
    items_discarded: int = 0

    # Research stats
    items_researched: int = 0
    research_failed: int = 0

    # Report
    report_id: str | None = None
    report_items: int = 0

    @property
    def summary(self) -> str:
        parts = []
        if self.items_fetched:
            parts.append(f"Fetched {self.items_fetched} from {len(self.sources_polled)} sources")
        if self.items_triaged:
            parts.append(f"Triaged: {self.items_passed} passed, {self.items_discarded} discarded")
        if self.items_researched:
            parts.append(f"Researched {self.items_researched} items")
        if self.report_id:
            parts.append(f"Report {self.report_id[:8]} with {self.report_items} items")
        return " | ".join(parts) if parts else "Nothing to process"


class RadarPipeline:
    """Orchestrates the full radar flow: poll → triage → research → report."""

    def __init__(
        self,
        db: sqlite3.Connection,
        settings: BlahSettings,
        adapters: dict[str, PlatformAdapter],
    ):
        self._db = db
        self._settings = settings
        self._adapters = adapters

        # Repos
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)
        self._report_repo = ReportRepo(db)
        self._report_item_repo = ReportItemRepo(db)
        self._piece_repo = PieceRepo(db)
        self._metrics_repo = PieceMetricsRepo(db)

        # Memory provider
        memory = FileMemoryProvider(
            context_path=settings.context_path,
            memory_json_path=settings.memory_json_path,
        )

        # Services
        self._triage = TriageService(db, settings, memory=memory)
        self._research = ResearchService(db, settings, adapters, memory=memory)

        # Notification endpoint (best-effort, never blocks pipeline)
        router_url = os.environ.get("ROUTER_URL") or f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8080')}"
        self._notify_url = f"{router_url}/notifications/push"

    def run(self, skip_poll: bool = False) -> PipelineResult:
        """Run the full pipeline.

        Args:
            skip_poll: If True, skip polling and use existing raw items

        Returns:
            PipelineResult with stats from each stage
        """
        result = PipelineResult()

        # 0. Warm up LLM endpoints (Modal cold start can take 60-90s)
        self._warmup_endpoints()

        # 1. Poll sources for new items
        if not skip_poll:
            poll_result = self._poll_sources()
            result.sources_polled = poll_result["sources"]
            result.items_fetched = poll_result["items_count"]

        # 2. Triage raw items
        triage_result = self._triage.triage_raw_items()
        result.items_triaged = triage_result.total
        result.items_passed = len(triage_result.passed)
        result.items_discarded = len(triage_result.discarded)

        # 3. Research triaged items (includes any leftover from prior runs)
        research_result = self._research.research_triaged_items()
        result.items_researched = len(research_result.researched)
        result.research_failed = len(research_result.failed)

        # 4. Generate report from researched items
        if result.items_researched > 0:
            report = self._generate_report(result.sources_polled)
            result.report_id = report["id"]
            result.report_items = report["item_count"]

        logger.info("Pipeline complete: %s", result.summary)

        # Best-effort notification
        if result.report_id:
            self._notify(
                "info", f"Report ready: {result.report_items} signals from {len(result.sources_polled)} sources",
                metadata={"report_id": result.report_id},
            )

        return result

    def poll_only(self) -> dict:
        """Just poll sources, don't triage/research/report."""
        return self._poll_sources()

    def _poll_sources(self) -> dict:
        """Fetch new items from all enabled sources."""
        sources = self._source_repo.list_all(enabled_only=True)
        if not sources:
            logger.info("No enabled sources to poll")
            return {"sources": [], "items_count": 0}

        total_items = 0
        polled_sources = []

        for source in sources:
            platform = source["platform"]

            # Platforms without API adapters are scraped via browser by the agent
            adapter = self._adapters.get(platform)
            if not adapter:
                logger.info(
                    "Skipping %s source %s (requires browser scraping)",
                    platform, source["id"][:8],
                )
                continue

            try:
                items = self._fetch_source(source, adapter)
                total_items += len(items)
                polled_sources.append(source["id"])
                logger.info(
                    "Polled source %s (%s): %d items",
                    source["id"][:8], platform, len(items),
                )
            except Exception as e:
                logger.exception("Failed to poll source %s: %s", source["id"], e)
                self._notify(
                    "warning", f"Failed to poll {platform} source {source['id'][:8]}: {e}",
                )

        return {"sources": polled_sources, "items_count": total_items}

    def _fetch_source(self, source: dict, adapter: PlatformAdapter) -> list[dict]:
        """Fetch items from a single source."""
        source_type = source.get("type")
        config = source.get("config", {})
        state = source.get("state", {})
        cursor = state.get("cursor")

        items = []

        if source_type == "account":
            # Fetch author's feed
            handle = config.get("handle")
            if handle:
                result = adapter.get_author_feed(handle, limit=30, cursor=cursor)
                items = result.get("items", [])
                new_cursor = result.get("cursor")
                if new_cursor:
                    self._source_repo.update(
                        source["id"], state={"cursor": new_cursor}
                    )

        elif source_type == "timeline":
            # Fetch home timeline
            result = adapter.get_timeline(limit=50, cursor=cursor)
            items = result.get("items", [])
            new_cursor = result.get("cursor")
            if new_cursor:
                self._source_repo.update(
                    source["id"], state={"cursor": new_cursor}
                )

        elif source_type == "search":
            # Search for posts
            query = config.get("query")
            if query:
                items = adapter.search_posts(query, limit=25)

        elif source_type == "subreddit":
            # Fetch subreddit feed (Reddit-specific)
            subreddit = config.get("subreddit")
            if subreddit and hasattr(adapter, "get_subreddit_feed"):
                result = adapter.get_subreddit_feed(subreddit, limit=30)
                items = result.get("items", [])

        elif source_type == "frontpage":
            # Fetch frontpage stories (HackerNews-specific)
            sort = config.get("sort", "top")
            if hasattr(adapter, "get_frontpage"):
                result = adapter.get_frontpage(sort, limit=30)
                items = result.get("items", [])

        elif source_type == "channel":
            # Fetch channel messages (Discord-specific)
            channel_id = config.get("channel_id")
            if channel_id and hasattr(adapter, "get_channel_messages"):
                guild_id = config.get("server_id", "")
                channel_name = config.get("label", "")
                items = adapter.get_channel_messages(
                    channel_id, limit=50, guild_id=guild_id, channel_name=channel_name
                )

        # Store items (with deduplication)
        stored = []
        for item in items:
            external_id = item.get("uri") or item.get("external_id")
            if not external_id:
                continue

            # Check if we already have this item
            existing = self._feed_repo.get_by_external_id(
                source["platform"], external_id
            )
            if existing:
                continue

            # Extract author info
            author = item.get("author", {})
            author_str = author.get("handle") if isinstance(author, dict) else str(author)

            # Create feed item
            feed_item = self._feed_repo.create(
                source_id=source["id"],
                platform=source["platform"],
                external_id=external_id,
                author=author_str,
                content=item.get("text", ""),
                url=item.get("url"),
            )
            stored.append(feed_item)

        return stored

    def _notify(self, level: str, title: str, body: str | None = None, metadata: dict | None = None) -> None:
        """Push a notification to the MCP router. Logs failures but doesn't block the pipeline."""
        try:
            httpx.post(
                self._notify_url,
                json={"level": level, "source": "blah-radar", "title": title, "body": body, "metadata": metadata},
                timeout=2,
            )
        except Exception:
            logger.warning("Failed to push notification: %s", title, exc_info=True)

    def _warmup_endpoints(self) -> None:
        """Warm up unique LLM endpoints before pipeline stages."""
        seen: set[str] = set()
        for model_cfg in [self._settings.models.triage, self._settings.models.research]:
            if model_cfg.provider != "openai" or not model_cfg.base_url:
                continue
            if model_cfg.base_url in seen:
                continue
            seen.add(model_cfg.base_url)
            logger.info("Warming up LLM endpoint: %s", model_cfg.base_url)
            client = LLMClient(
                provider=model_cfg.provider,
                model=model_cfg.model,
                base_url=model_cfg.base_url,
            )
            if not client.warmup():
                logger.warning("LLM endpoint did not warm up in time — continuing anyway")

    def _generate_report(self, sources_polled: list[str]) -> dict:
        """Generate a report from researched items."""
        # Get all researched items not yet in a report
        items = self._feed_repo.list_by_status("researched", limit=500)

        if not items:
            logger.info("No researched items for report")
            return {"id": None, "item_count": 0}

        # Create the report
        report = self._report_repo.create(sources_polled=sources_polled)

        # Create report items from feed items
        for item in items:
            enrichment = item.get("enrichment", {})

            # Create a report item (signal type)
            self._report_item_repo.create(
                report_id=report["id"],
                item_type="signal",
                data={
                    "feed_item_id": item["id"],
                    "url": item.get("url"),
                    "author": item.get("author"),
                    "content": item.get("content"),
                    "suggested_angles": enrichment.get("suggested_angles", []),
                    "relevance_notes": enrichment.get("relevance_notes"),
                    "author_context": enrichment.get("author_context"),
                },
                relevance_score=item.get("relevance_score"),
            )

            # Update feed item to link to report
            self._feed_repo.update(item["id"], status="reported", report_id=report["id"])

        item_count = len(items)
        logger.info("Generated report %s with %d items", report["id"][:8], item_count)

        return {"id": report["id"], "item_count": item_count}

    def track_published_pieces(self) -> dict:
        """Fetch engagement metrics for published pieces and store snapshots.

        Returns:
            dict with "tracked" count and "failed" count
        """
        pieces = self._piece_repo.list_published()
        if not pieces:
            logger.info("No published pieces to track")
            return {"tracked": 0, "failed": 0}

        tracked = 0
        failed = 0

        for piece in pieces:
            platform = piece.get("platform")
            external_id = piece.get("external_id")

            if not platform or not external_id:
                continue

            adapter = self._adapters.get(platform)
            if not adapter:
                logger.debug("No adapter for %s, skipping piece %s", platform, piece["id"][:8])
                continue

            try:
                post_data = adapter.get_post(external_id)
                if not post_data:
                    logger.warning("Could not fetch post %s on %s", external_id, platform)
                    failed += 1
                    continue

                self._metrics_repo.create(
                    piece_id=piece["id"],
                    platform=platform,
                    like_count=post_data.get("like_count", 0),
                    repost_count=post_data.get("repost_count", 0),
                    reply_count=post_data.get("reply_count", 0),
                    raw_data=post_data,
                )
                tracked += 1
                logger.info(
                    "Tracked metrics for piece %s: %d likes, %d reposts, %d replies",
                    piece["id"][:8],
                    post_data.get("like_count", 0),
                    post_data.get("repost_count", 0),
                    post_data.get("reply_count", 0),
                )
            except Exception:
                logger.exception("Failed to track metrics for piece %s", piece["id"][:8])
                failed += 1

        logger.info("Piece tracking complete: %d tracked, %d failed", tracked, failed)
        return {"tracked": tracked, "failed": failed}
