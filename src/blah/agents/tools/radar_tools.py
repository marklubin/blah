"""Tools for Radar agents — config and report management."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.adapters.base import PlatformAdapter, PostContent
from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import FeedItemRepo, ReportItemRepo, ReportRepo, SourceRepo

logger = logging.getLogger(__name__)


class RadarConfigTools:
    """Tools for configuring radar sources."""

    def __init__(self, db: sqlite3.Connection, adapters: dict[str, PlatformAdapter]):
        self._db = db
        self._source_repo = SourceRepo(db)
        self._adapters = adapters

    @tool(
        name="add_source",
        description="Add a new source to monitor. Types: account (user), timeline (home), search.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform name: 'bluesky' or 'twitter'",
                    "enum": ["bluesky", "twitter"],
                },
                "source_type": {
                    "type": "string",
                    "description": "Type of source: 'account', 'timeline', or 'search'",
                    "enum": ["account", "timeline", "search"],
                },
                "handle": {
                    "type": "string",
                    "description": "For account type: the user handle (e.g., karpathy.bsky.social)",
                },
                "query": {
                    "type": "string",
                    "description": "For 'search' type: the search query",
                },
                "label": {
                    "type": "string",
                    "description": "Optional friendly label for this source",
                },
            },
            "required": ["platform", "source_type"],
        },
    )
    def add_source(
        self,
        platform: str,
        source_type: str,
        handle: str | None = None,
        query: str | None = None,
        label: str | None = None,
    ) -> ToolResult:
        # Validate based on type
        if source_type == "account" and not handle:
            return ToolResult(
                content="Error: 'handle' is required for account sources",
                is_error=True,
            )
        if source_type == "search" and not query:
            return ToolResult(
                content="Error: 'query' is required for search sources",
                is_error=True,
            )

        # Build config
        config = {}
        if handle:
            config["handle"] = handle
        if query:
            config["query"] = query

        # Generate label if not provided
        if not label:
            if source_type == "account":
                label = f"@{handle}"
            elif source_type == "timeline":
                label = f"{platform} timeline"
            elif source_type == "search":
                label = f'search: "{query}"'

        # Store label in config
        config["label"] = label

        # Create the source
        source = self._source_repo.create(
            platform=platform,
            source_type=source_type,
            config=config,
        )

        return ToolResult(
            content=json.dumps({
                "success": True,
                "source_id": source["id"],
                "message": f"Added {source_type} source: {label}",
            }),
        )

    @tool(
        name="remove_source",
        description="Remove a source from monitoring.",
        parameters={
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "The ID of the source to remove",
                },
            },
            "required": ["source_id"],
        },
    )
    def remove_source(self, source_id: str) -> ToolResult:
        source = self._source_repo.get(source_id)
        if not source:
            return ToolResult(
                content=f"Error: Source {source_id} not found",
                is_error=True,
            )

        self._source_repo.delete(source_id)
        return ToolResult(
            content=json.dumps({
                "success": True,
                "message": f"Removed source: {source.get('label', source_id)}",
            }),
        )

    @tool(
        name="list_sources",
        description="List all configured sources.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Optional: filter by platform",
                },
            },
        },
    )
    def list_sources(self, platform: str | None = None) -> ToolResult:
        if platform:
            sources = self._source_repo.list_by_platform(platform)
        else:
            sources = self._source_repo.list_all()

        if not sources:
            return ToolResult(content="No sources configured yet.")

        lines = ["Configured sources:"]
        for s in sources:
            enabled = "✓" if s.get("enabled", True) else "✗"
            config = s.get("config", {})
            label = config.get("label") or s.get("id")[:8]
            lines.append(
                f"  [{enabled}] {s['platform']}/{s['type']}: {label} (id: {s['id'][:8]})"
            )

        return ToolResult(content="\n".join(lines))

    @tool(
        name="toggle_source",
        description="Enable or disable a source.",
        parameters={
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "The ID of the source",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable",
                },
            },
            "required": ["source_id", "enabled"],
        },
    )
    def toggle_source(self, source_id: str, enabled: bool) -> ToolResult:
        source = self._source_repo.get(source_id)
        if not source:
            return ToolResult(
                content=f"Error: Source {source_id} not found",
                is_error=True,
            )

        self._source_repo.update(source_id, enabled=enabled)
        status = "enabled" if enabled else "disabled"
        config = source.get("config", {})
        label = config.get("label", source_id[:8])
        return ToolResult(
            content=f"Source {label} {status}",
        )

    @tool(
        name="search_posts",
        description="Search for posts on a platform to discover interesting accounts.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform to search: 'bluesky' or 'twitter'",
                    "enum": ["bluesky", "twitter"],
                },
                "query": {
                    "type": "string",
                    "description": "Search query (keywords, topics, etc.)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10)",
                },
            },
            "required": ["platform", "query"],
        },
    )
    def search_posts(
        self, platform: str, query: str, limit: int = 10
    ) -> ToolResult:
        adapter = self._adapters.get(platform)
        if not adapter:
            return ToolResult(
                content=f"Error: No adapter configured for {platform}",
                is_error=True,
            )

        try:
            posts = adapter.search_posts(query, limit=limit)
            if not posts:
                return ToolResult(content=f"No posts found for '{query}' on {platform}")

            lines = [f"Search results for '{query}' on {platform}:\n"]
            for i, post in enumerate(posts, 1):
                author = post.get("author", {})
                handle = author.get("handle", "unknown") if isinstance(author, dict) else author
                text = post.get("text", "")[:100]
                url = post.get("url", "")
                lines.append(f"{i}. @{handle}")
                lines.append(f"   {text}...")
                if url:
                    lines.append(f"   {url}")
                lines.append("")

            return ToolResult(content="\n".join(lines))
        except Exception as e:
            logger.exception("Search posts failed: %s", e)
            return ToolResult(content=f"Error searching: {e}", is_error=True)

    @tool(
        name="get_profile",
        description="Get a user's profile. Use to learn about someone before adding as a source.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform: 'bluesky' or 'twitter'",
                    "enum": ["bluesky", "twitter"],
                },
                "handle": {
                    "type": "string",
                    "description": "User handle (e.g., karpathy.bsky.social)",
                },
            },
            "required": ["platform", "handle"],
        },
    )
    def get_profile(self, platform: str, handle: str) -> ToolResult:
        adapter = self._adapters.get(platform)
        if not adapter:
            return ToolResult(
                content=f"Error: No adapter configured for {platform}",
                is_error=True,
            )

        try:
            profile = adapter.get_profile(handle)
            if not profile:
                return ToolResult(content=f"Profile not found: @{handle}")

            lines = [
                f"**@{profile.get('handle', handle)}**",
            ]
            if profile.get("display_name"):
                lines.append(f"Name: {profile['display_name']}")
            if profile.get("description"):
                lines.append(f"Bio: {profile['description']}")
            if profile.get("followers_count"):
                lines.append(f"Followers: {profile['followers_count']:,}")
            if profile.get("follows_count"):
                lines.append(f"Following: {profile['follows_count']:,}")
            if profile.get("posts_count"):
                lines.append(f"Posts: {profile['posts_count']:,}")

            return ToolResult(content="\n".join(lines))
        except Exception as e:
            logger.exception("Get profile failed: %s", e)
            return ToolResult(content=f"Error fetching profile: {e}", is_error=True)

    @tool(
        name="get_recent_posts",
        description="Get recent posts from a user to preview their content.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform: 'bluesky' or 'twitter'",
                    "enum": ["bluesky", "twitter"],
                },
                "handle": {
                    "type": "string",
                    "description": "User handle",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max posts to return (default 5)",
                },
            },
            "required": ["platform", "handle"],
        },
    )
    def get_recent_posts(
        self, platform: str, handle: str, limit: int = 5
    ) -> ToolResult:
        adapter = self._adapters.get(platform)
        if not adapter:
            return ToolResult(
                content=f"Error: No adapter configured for {platform}",
                is_error=True,
            )

        try:
            result = adapter.get_author_feed(handle, limit=limit)
            posts = result.get("items", [])
            if not posts:
                return ToolResult(content=f"No recent posts from @{handle}")

            lines = [f"Recent posts from @{handle}:\n"]
            for i, post in enumerate(posts, 1):
                text = post.get("text", "")[:150]
                url = post.get("url", "")
                likes = post.get("like_count", 0)
                lines.append(f"{i}. {text}...")
                if likes:
                    lines.append(f"   ❤️ {likes}")
                if url:
                    lines.append(f"   {url}")
                lines.append("")

            return ToolResult(content="\n".join(lines))
        except Exception as e:
            logger.exception("Get recent posts failed: %s", e)
            return ToolResult(content=f"Error fetching posts: {e}", is_error=True)


class RadarReportTools:
    """Tools for reviewing radar reports and engaging."""

    def __init__(
        self,
        db: sqlite3.Connection,
        adapters: dict[str, PlatformAdapter],
        report_id: str | None = None,
    ):
        self._db = db
        self._adapters = adapters
        self._report_id = report_id
        self._report_repo = ReportRepo(db)
        self._report_item_repo = ReportItemRepo(db)
        self._feed_item_repo = FeedItemRepo(db)

    def set_report_id(self, report_id: str) -> None:
        """Set the current report being reviewed."""
        self._report_id = report_id

    @tool(
        name="list_report_items",
        description="List items in the current report with their suggested engagement angles.",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'new', 'reviewed', 'skipped'",
                    "enum": ["new", "reviewed", "skipped"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum items to return (default 10)",
                },
            },
        },
    )
    def list_report_items(
        self, status: str | None = None, limit: int = 10
    ) -> ToolResult:
        if not self._report_id:
            return ToolResult(
                content="Error: No report selected",
                is_error=True,
            )

        items = self._report_item_repo.list_by_report(self._report_id)
        if status:
            items = [i for i in items if i.get("status") == status]

        items = items[:limit]

        if not items:
            return ToolResult(content="No items found.")

        lines = []
        for i, item in enumerate(items, 1):
            data = item.get("data", {})
            author = data.get("author", "unknown")
            content = data.get("content", "")[:100]
            angles = data.get("suggested_angles", [])
            relevance = data.get("relevance_notes", "")
            score = item.get("relevance_score", 0)
            item_status = item.get("status", "new")

            lines.append(f"\n**[{i}] @{author}** (score: {score:.2f}, {item_status})")
            lines.append(f"   {content}...")
            if relevance:
                lines.append(f"   *Why relevant:* {relevance}")
            if angles:
                lines.append("   *Suggested angles:*")
                for angle in angles[:2]:
                    lines.append(f"     - {angle[:80]}...")
            lines.append(f"   [item_id: {item['id'][:8]}]")

        return ToolResult(content="\n".join(lines))

    @tool(
        name="get_item_detail",
        description="Get full details for a report item including suggested angles and context.",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID (can use first 8 chars)",
                },
            },
            "required": ["item_id"],
        },
    )
    def get_item_detail(self, item_id: str) -> ToolResult:
        # Try to find the item (support partial IDs)
        items = self._report_item_repo.list_by_report(self._report_id or "")
        item = None
        for i in items:
            if i["id"].startswith(item_id):
                item = i
                break

        if not item:
            return ToolResult(
                content=f"Error: Item {item_id} not found",
                is_error=True,
            )

        data = item.get("data", {})
        lines = [
            f"**Author:** @{data.get('author', 'unknown')}",
            f"**URL:** {data.get('url', 'N/A')}",
            f"**Score:** {item.get('relevance_score', 0):.2f}",
            f"**Status:** {item.get('status', 'new')}",
            "",
            "**Content:**",
            data.get("content", "(no content)"),
            "",
        ]

        if data.get("relevance_notes"):
            lines.extend([
                "**Why This Is Relevant:**",
                data["relevance_notes"],
                "",
            ])

        if data.get("author_context"):
            lines.extend([
                "**About the Author:**",
                data["author_context"],
                "",
            ])

        angles = data.get("suggested_angles", [])
        if angles:
            lines.append("**Suggested Engagement Angles:**")
            for j, angle in enumerate(angles, 1):
                lines.append(f"  {j}. {angle}")

        return ToolResult(content="\n".join(lines))

    @tool(
        name="mark_reviewed",
        description="Mark a report item as reviewed (you've seen it, may or may not engage).",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID",
                },
            },
            "required": ["item_id"],
        },
    )
    def mark_reviewed(self, item_id: str) -> ToolResult:
        items = self._report_item_repo.list_by_report(self._report_id or "")
        for item in items:
            if item["id"].startswith(item_id):
                self._report_item_repo.update(item["id"], status="reviewed")
                return ToolResult(content=f"Marked item {item_id[:8]} as reviewed")

        return ToolResult(
            content=f"Error: Item {item_id} not found",
            is_error=True,
        )

    @tool(
        name="mark_skipped",
        description="Mark a report item as skipped (not interested in engaging).",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID",
                },
            },
            "required": ["item_id"],
        },
    )
    def mark_skipped(self, item_id: str) -> ToolResult:
        items = self._report_item_repo.list_by_report(self._report_id or "")
        for item in items:
            if item["id"].startswith(item_id):
                self._report_item_repo.update(item["id"], status="skipped")
                return ToolResult(content=f"Marked item {item_id[:8]} as skipped")

        return ToolResult(
            content=f"Error: Item {item_id} not found",
            is_error=True,
        )

    @tool(
        name="draft_reply",
        description="Draft a reply to a post. Returns the draft for review before sending.",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID to reply to",
                },
                "reply_text": {
                    "type": "string",
                    "description": "The text of the reply",
                },
            },
            "required": ["item_id", "reply_text"],
        },
    )
    def draft_reply(self, item_id: str, reply_text: str) -> ToolResult:
        # Find the item
        items = self._report_item_repo.list_by_report(self._report_id or "")
        item = None
        for i in items:
            if i["id"].startswith(item_id):
                item = i
                break

        if not item:
            return ToolResult(
                content=f"Error: Item {item_id} not found",
                is_error=True,
            )

        # Check character limits
        data = item.get("data", {})
        feed_item_id = data.get("feed_item_id")
        if feed_item_id:
            feed_item = self._feed_item_repo.get(feed_item_id)
            platform = feed_item.get("platform", "bluesky") if feed_item else "bluesky"
        else:
            platform = "bluesky"

        limit = 300 if platform == "bluesky" else 280
        if len(reply_text) > limit:
            msg = f"Reply is {len(reply_text)} chars, exceeds {platform} limit ({limit})"
            return ToolResult(content=f"Error: {msg}", is_error=True)

        # Store the draft in item data
        self._report_item_repo.update(
            item["id"],
            data={**data, "draft_reply": reply_text},
        )

        return ToolResult(
            content=json.dumps({
                "success": True,
                "item_id": item["id"][:8],
                "reply_text": reply_text,
                "char_count": len(reply_text),
                "platform": platform,
                "message": "Draft saved. Use send_reply to post it.",
            }),
        )

    @tool(
        name="send_reply",
        description="Send a drafted reply to a post.",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID to reply to",
                },
            },
            "required": ["item_id"],
        },
    )
    def send_reply(self, item_id: str) -> ToolResult:
        # Find the item
        items = self._report_item_repo.list_by_report(self._report_id or "")
        item = None
        for i in items:
            if i["id"].startswith(item_id):
                item = i
                break

        if not item:
            return ToolResult(
                content=f"Error: Item {item_id} not found",
                is_error=True,
            )

        data = item.get("data", {})
        draft = data.get("draft_reply")
        if not draft:
            return ToolResult(
                content="Error: No draft reply found. Use draft_reply first.",
                is_error=True,
            )

        # Get the feed item to find the post URI
        feed_item_id = data.get("feed_item_id")
        if not feed_item_id:
            return ToolResult(
                content="Error: No feed item linked",
                is_error=True,
            )

        feed_item = self._feed_item_repo.get(feed_item_id)
        if not feed_item:
            return ToolResult(
                content="Error: Feed item not found",
                is_error=True,
            )

        platform = feed_item.get("platform", "bluesky")
        adapter = self._adapters.get(platform)
        if not adapter:
            return ToolResult(
                content=f"Error: No adapter for platform {platform}",
                is_error=True,
            )

        # Post the reply
        try:
            external_id = feed_item.get("external_id")
            result = adapter.post(PostContent(
                text=draft,
                reply_to=external_id,
            ))

            # Update the report item
            self._report_item_repo.update(
                item["id"],
                status="actioned",
                data={
                    **data,
                    "reply_uri": result.external_id,
                    "reply_url": result.external_url,
                },
            )

            return ToolResult(
                content=json.dumps({
                    "success": True,
                    "reply_url": result.external_url,
                    "message": "Reply posted successfully!",
                }),
            )
        except Exception as e:
            logger.exception("Failed to send reply: %s", e)
            return ToolResult(
                content=f"Error posting reply: {e}",
                is_error=True,
            )

    @tool(
        name="follow_author",
        description="Follow the author of a post.",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "The report item ID (will follow that post's author)",
                },
            },
            "required": ["item_id"],
        },
    )
    def follow_author(self, item_id: str) -> ToolResult:
        # Find the item
        items = self._report_item_repo.list_by_report(self._report_id or "")
        item = None
        for i in items:
            if i["id"].startswith(item_id):
                item = i
                break

        if not item:
            return ToolResult(
                content=f"Error: Item {item_id} not found",
                is_error=True,
            )

        data = item.get("data", {})
        author = data.get("author")
        if not author:
            return ToolResult(
                content="Error: No author found for this item",
                is_error=True,
            )

        # Get the feed item to determine platform
        feed_item_id = data.get("feed_item_id")
        if feed_item_id:
            feed_item = self._feed_item_repo.get(feed_item_id)
            platform = feed_item.get("platform", "bluesky") if feed_item else "bluesky"
        else:
            platform = "bluesky"

        adapter = self._adapters.get(platform)
        if not adapter:
            return ToolResult(
                content=f"Error: No adapter for platform {platform}",
                is_error=True,
            )

        try:
            success = adapter.follow(author)
            if success:
                return ToolResult(
                    content=f"Now following @{author} on {platform}",
                )
            return ToolResult(
                content=f"Failed to follow @{author}",
                is_error=True,
            )
        except Exception as e:
            logger.exception("Failed to follow: %s", e)
            return ToolResult(
                content=f"Error following @{author}: {e}",
                is_error=True,
            )

    @tool(
        name="get_report_summary",
        description="Get a summary of the current report.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_report_summary(self) -> ToolResult:
        if not self._report_id:
            return ToolResult(
                content="Error: No report selected",
                is_error=True,
            )

        report = self._report_repo.get(self._report_id)
        if not report:
            return ToolResult(
                content="Error: Report not found",
                is_error=True,
            )

        items = self._report_item_repo.list_by_report(self._report_id)
        new = len([i for i in items if i.get("status") == "new"])
        reviewed = len([i for i in items if i.get("status") == "reviewed"])
        skipped = len([i for i in items if i.get("status") == "skipped"])
        actioned = len([i for i in items if i.get("status") == "actioned"])

        lines = [
            f"**Report ID:** {self._report_id[:8]}",
            f"**Created:** {report.get('created_at', 'unknown')}",
            f"**Status:** {report.get('status', 'pending')}",
            "",
            "**Items:**",
            f"  - New: {new}",
            f"  - Reviewed: {reviewed}",
            f"  - Skipped: {skipped}",
            f"  - Actioned: {actioned}",
            f"  - Total: {len(items)}",
        ]

        return ToolResult(content="\n".join(lines))

    @tool(
        name="complete_report",
        description="Mark the current report as complete (finished reviewing).",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def complete_report(self) -> ToolResult:
        if not self._report_id:
            return ToolResult(
                content="Error: No report selected",
                is_error=True,
            )

        self._report_repo.update(self._report_id, status="complete")
        return ToolResult(content=f"Report {self._report_id[:8]} marked as complete")
