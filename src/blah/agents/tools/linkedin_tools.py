"""Tools for LinkedIn scraping and ingestion via browser MCP."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import FeedItemRepo, SourceRepo

logger = logging.getLogger(__name__)


class LinkedInTools:
    """Tools for LinkedIn browser scraping and data ingestion."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)

    @tool(
        name="store_linkedin_items",
        description="Store scraped LinkedIn posts as feed items for pipeline processing.",
        parameters={
            "type": "object",
            "properties": {
                "items_json": {
                    "type": "string",
                    "description": "JSON array of scraped posts. Each post: {external_id, url, author, text, created_at, like_count, reply_count}",
                },
            },
            "required": ["items_json"],
        },
    )
    def store_linkedin_items(self, items_json: str) -> ToolResult:
        try:
            items = json.loads(items_json)
        except json.JSONDecodeError as e:
            return ToolResult(content=f"Error: Invalid JSON: {e}", is_error=True)

        if not isinstance(items, list):
            return ToolResult(content="Error: Expected a JSON array", is_error=True)

        # Find or create LinkedIn source
        sources = self._source_repo.list_by_platform("linkedin")
        if sources:
            source_id = sources[0]["id"]
        else:
            source = self._source_repo.create(
                platform="linkedin",
                source_type="feed",
                config={"label": "LinkedIn feed (scraped)"},
            )
            source_id = source["id"]

        # Normalize and store
        batch = []
        for item in items:
            batch.append({
                "source_id": source_id,
                "platform": "linkedin",
                "external_id": item.get("external_id", ""),
                "author": item.get("author", ""),
                "content": item.get("text") or item.get("content", ""),
                "url": item.get("url", ""),
            })

        result = self._feed_repo.create_batch(batch)

        return ToolResult(
            content=json.dumps({
                "success": True,
                "ingested": result["ingested"],
                "skipped": result["skipped"],
                "source_id": source_id,
                "message": f"Stored {result['ingested']} LinkedIn posts ({result['skipped']} duplicates skipped)",
            }),
        )

    @tool(
        name="check_linkedin_auth",
        description="Get instructions for checking LinkedIn authentication status in the browser.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def check_linkedin_auth(self) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "instructions": [
                    "Use mcp__claude_ai_router__browser_navigate to go to https://www.linkedin.com/feed/",
                    "Use mcp__claude_ai_router__browser_get_rendered_content to extract page content",
                    "Look for auth indicators:",
                    "  - Logged in: 'Start a post', 'My Network', 'Messaging'",
                    "  - Logged out: 'Sign in', 'Join now', 'Sign in to LinkedIn'",
                    "Report the auth status back",
                ],
                "browser_tools": "mcp__claude_ai_router__browser_*",
                "note": "You MUST use the MCP router browser tools (mcp__claude_ai_router__browser_*), not browser-use tools. The router browser has the logged-in LinkedIn session.",
                "url": "https://www.linkedin.com/feed/",
                "logged_in_indicators": ["Start a post", "My Network", "Messaging"],
                "logged_out_indicators": ["Sign in", "Join now"],
            }),
        )

    @tool(
        name="get_scrape_instructions",
        description="Get instructions for scraping a specific LinkedIn source type.",
        parameters={
            "type": "object",
            "properties": {
                "scrape_type": {
                    "type": "string",
                    "description": "Type of scrape: 'feed', 'profile', or 'search'",
                    "enum": ["feed", "profile", "search"],
                },
                "target": {
                    "type": "string",
                    "description": "For profile: LinkedIn handle/slug. For search: search query. Ignored for feed.",
                },
            },
            "required": ["scrape_type"],
        },
    )
    def get_scrape_instructions(self, scrape_type: str, target: str | None = None) -> ToolResult:
        browser_note = (
            "IMPORTANT: Use the MCP router browser tools (mcp__claude_ai_router__browser_*), "
            "NOT browser-use tools. The router browser has the logged-in LinkedIn session."
        )

        if scrape_type == "feed":
            return ToolResult(
                content=json.dumps({
                    "url": "https://www.linkedin.com/feed/",
                    "browser_tools": "mcp__claude_ai_router__browser_*",
                    "note": browser_note,
                    "instructions": [
                        "Use mcp__claude_ai_router__browser_navigate to go to https://www.linkedin.com/feed/",
                        "Use mcp__claude_ai_router__browser_get_rendered_content to extract page content",
                        "Scroll down with mcp__claude_ai_router__browser_evaluate (window.scrollBy) to load more posts",
                        "Extract post content including: author name, post text, like count, comment count",
                        "For each post, extract the activity URN from the post URL if visible",
                        "Format as JSON array and call store_linkedin_items",
                    ],
                    "extract_fields": ["author", "text", "url", "like_count", "reply_count", "external_id"],
                }),
            )
        elif scrape_type == "profile":
            if not target:
                return ToolResult(content="Error: target (LinkedIn handle) required for profile scrape", is_error=True)
            return ToolResult(
                content=json.dumps({
                    "url": f"https://www.linkedin.com/in/{target}/recent-activity/all/",
                    "browser_tools": "mcp__claude_ai_router__browser_*",
                    "note": browser_note,
                    "instructions": [
                        f"Use mcp__claude_ai_router__browser_navigate to go to https://www.linkedin.com/in/{target}/recent-activity/all/",
                        "Use mcp__claude_ai_router__browser_get_rendered_content to extract posts",
                        "Format as JSON array and call store_linkedin_items",
                    ],
                    "extract_fields": ["author", "text", "url", "like_count", "reply_count", "external_id"],
                }),
            )
        elif scrape_type == "search":
            if not target:
                return ToolResult(content="Error: target (search query) required for search scrape", is_error=True)
            from urllib.parse import quote_plus
            return ToolResult(
                content=json.dumps({
                    "url": f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(target)}",
                    "browser_tools": "mcp__claude_ai_router__browser_*",
                    "note": browser_note,
                    "instructions": [
                        f"Use mcp__claude_ai_router__browser_navigate to search LinkedIn for '{target}'",
                        "Use mcp__claude_ai_router__browser_get_rendered_content to extract matching posts",
                        "Format as JSON array and call store_linkedin_items",
                    ],
                    "extract_fields": ["author", "text", "url", "like_count", "reply_count", "external_id"],
                }),
            )
        else:
            return ToolResult(content=f"Error: Unknown scrape type: {scrape_type}", is_error=True)

    @tool(
        name="get_linkedin_sources",
        description="List configured LinkedIn sources from the database.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_linkedin_sources(self) -> ToolResult:
        sources = self._source_repo.list_by_platform("linkedin")
        if not sources:
            return ToolResult(content="No LinkedIn sources configured.")

        lines = ["LinkedIn sources:"]
        for s in sources:
            enabled = "+" if s.get("enabled", True) else "-"
            config = s.get("config", {})
            label = config.get("label") or s["id"][:8]
            state = s.get("state", {})
            last_scrape = state.get("last_scrape", "never")
            auth_status = state.get("auth_status", "unknown")
            lines.append(
                f"  [{enabled}] {s['type']}: {label} (auth: {auth_status}, last scrape: {last_scrape})"
            )

        return ToolResult(content="\n".join(lines))
