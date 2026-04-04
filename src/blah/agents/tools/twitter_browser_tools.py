"""Browser scraping tools for Twitter/X via MCP router."""

from __future__ import annotations

import json
import logging
import sqlite3
from urllib.parse import quote_plus

from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import FeedItemRepo, SourceRepo

logger = logging.getLogger(__name__)

BROWSER_NOTE = (
    "IMPORTANT: Use the MCP router browser tools (mcp__claude_ai_mcp-router__browser_*), "
    "NOT browser-use tools. The router browser has the persistent session."
)


class TwitterBrowserTools:
    """Tools for Twitter/X browser scraping and data ingestion."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)

    @tool(
        name="check_twitter_auth",
        description="Get instructions for checking Twitter/X authentication status in the browser.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def check_twitter_auth(self) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "instructions": [
                    "Use mcp__claude_ai_mcp-router__browser_navigate to go to https://x.com/home",
                    "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                    "Look for auth indicators:",
                    "  - Logged in: home timeline content, 'Post' button, user avatar",
                    "  - Logged out: 'Sign in' button, login form, 'Create your account'",
                    "Report the auth status back",
                ],
                "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                "note": BROWSER_NOTE,
                "url": "https://x.com/home",
                "logged_in_indicators": ["Post", "Home", "What is happening"],
                "logged_out_indicators": ["Sign in", "Create your account", "Log in"],
            }),
        )

    @tool(
        name="get_twitter_scrape_instructions",
        description="Get instructions for scraping a specific Twitter/X source type.",
        parameters={
            "type": "object",
            "properties": {
                "scrape_type": {
                    "type": "string",
                    "description": "Type of scrape: 'account', 'search', or 'timeline'",
                    "enum": ["account", "search", "timeline"],
                },
                "target": {
                    "type": "string",
                    "description": "For account: handle (without @). For search: query. Ignored for timeline.",
                },
            },
            "required": ["scrape_type"],
        },
    )
    def get_twitter_scrape_instructions(self, scrape_type: str, target: str | None = None) -> ToolResult:
        if scrape_type == "account":
            if not target:
                return ToolResult(content="Error: target (Twitter handle) required for account scrape", is_error=True)
            handle = target.lstrip("@")
            return ToolResult(
                content=json.dumps({
                    "url": f"https://x.com/{handle}",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to go to https://x.com/{handle}",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract tweets",
                        "Scroll down with mcp__claude_ai_mcp-router__browser_evaluate (window.scrollBy) to load more",
                        "Extract tweet data: text, author, like count, retweet count, reply count, tweet URL",
                        "The tweet ID is the last segment of the tweet URL (e.g. /status/12345)",
                        "Format as JSON array and call store_twitter_items",
                    ],
                    "extract_fields": ["external_id", "text", "author", "url", "like_count", "retweet_count", "reply_count"],
                }),
            )
        elif scrape_type == "search":
            if not target:
                return ToolResult(content="Error: target (search query) required for search scrape", is_error=True)
            return ToolResult(
                content=json.dumps({
                    "url": f"https://x.com/search?q={quote_plus(target)}&src=typed_query&f=live",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to search X for '{target}'",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract matching tweets",
                        "Extract tweet data: text, author, like count, retweet count, reply count, tweet URL",
                        "Format as JSON array and call store_twitter_items",
                    ],
                    "extract_fields": ["external_id", "text", "author", "url", "like_count", "retweet_count", "reply_count"],
                }),
            )
        elif scrape_type == "timeline":
            return ToolResult(
                content=json.dumps({
                    "url": "https://x.com/home",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        "Use mcp__claude_ai_mcp-router__browser_navigate to go to https://x.com/home",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract timeline tweets",
                        "Scroll down with mcp__claude_ai_mcp-router__browser_evaluate (window.scrollBy) to load more",
                        "Extract tweet data: text, author, like count, retweet count, reply count, tweet URL",
                        "Format as JSON array and call store_twitter_items",
                    ],
                    "extract_fields": ["external_id", "text", "author", "url", "like_count", "retweet_count", "reply_count"],
                }),
            )
        else:
            return ToolResult(content=f"Error: Unknown scrape type: {scrape_type}", is_error=True)

    @tool(
        name="store_twitter_items",
        description="Store scraped Twitter/X tweets as feed items for pipeline processing.",
        parameters={
            "type": "object",
            "properties": {
                "items_json": {
                    "type": "string",
                    "description": "JSON array of scraped tweets. Each: {external_id, url, author, text, like_count, retweet_count, reply_count}",
                },
            },
            "required": ["items_json"],
        },
    )
    def store_twitter_items(self, items_json: str) -> ToolResult:
        try:
            items = json.loads(items_json)
        except json.JSONDecodeError as e:
            return ToolResult(content=f"Error: Invalid JSON: {e}", is_error=True)

        if not isinstance(items, list):
            return ToolResult(content="Error: Expected a JSON array", is_error=True)

        # Find or create Twitter source
        sources = self._source_repo.list_by_platform("twitter")
        if sources:
            source_id = sources[0]["id"]
        else:
            source = self._source_repo.create(
                platform="twitter",
                source_type="feed",
                config={"label": "Twitter feed (scraped)"},
            )
            source_id = source["id"]

        # Normalize and store
        batch = []
        for item in items:
            batch.append({
                "source_id": source_id,
                "platform": "twitter",
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
                "message": f"Stored {result['ingested']} tweets ({result['skipped']} duplicates skipped)",
            }),
        )

    @tool(
        name="get_twitter_sources",
        description="List configured Twitter/X sources from the database.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_twitter_sources(self) -> ToolResult:
        sources = self._source_repo.list_by_platform("twitter")
        if not sources:
            return ToolResult(content="No Twitter sources configured.")

        lines = ["Twitter sources:"]
        for s in sources:
            enabled = "+" if s.get("enabled", True) else "-"
            config = s.get("config", {})
            label = config.get("label") or s["id"][:8]
            lines.append(
                f"  [{enabled}] {s['type']}: {label}"
            )

        return ToolResult(content="\n".join(lines))
