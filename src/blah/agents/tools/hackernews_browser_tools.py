"""Browser scraping tools for Hacker News via MCP router."""

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


class HackerNewsBrowserTools:
    """Tools for Hacker News browser scraping and data ingestion."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)

    @tool(
        name="check_hackernews_auth",
        description="Get instructions for checking Hacker News authentication status in the browser.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def check_hackernews_auth(self) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "instructions": [
                    "Use mcp__claude_ai_mcp-router__browser_navigate to go to https://news.ycombinator.com",
                    "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                    "Look for auth indicators:",
                    "  - Logged in: username link in top-right bar, 'logout' link",
                    "  - Logged out: 'login' link in top-right bar",
                    "Report the auth status back",
                ],
                "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                "note": BROWSER_NOTE,
                "url": "https://news.ycombinator.com",
                "logged_in_indicators": ["logout"],
                "logged_out_indicators": ["login"],
            }),
        )

    @tool(
        name="get_hackernews_scrape_instructions",
        description="Get instructions for scraping a specific Hacker News source type.",
        parameters={
            "type": "object",
            "properties": {
                "scrape_type": {
                    "type": "string",
                    "description": "Type of scrape: 'frontpage', 'search', or 'account'",
                    "enum": ["frontpage", "search", "account"],
                },
                "target": {
                    "type": "string",
                    "description": "For frontpage: sort type (top/new/best). For search: query. For account: username.",
                },
            },
            "required": ["scrape_type"],
        },
    )
    def get_hackernews_scrape_instructions(self, scrape_type: str, target: str | None = None) -> ToolResult:
        if scrape_type == "frontpage":
            sort_map = {
                "top": "https://news.ycombinator.com/",
                "new": "https://news.ycombinator.com/newest",
                "best": "https://news.ycombinator.com/best",
            }
            sort_key = target or "top"
            url = sort_map.get(sort_key, sort_map["top"])
            return ToolResult(
                content=json.dumps({
                    "url": url,
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to go to {url}",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                        "Extract story data: title, URL, points, author, comment count, HN item ID",
                        "The HN item ID is in the 'item?id=XXXXX' links",
                        "Format as JSON array and call store_hackernews_items",
                    ],
                    "extract_fields": ["external_id", "title", "url", "author", "points", "comment_count"],
                }),
            )
        elif scrape_type == "search":
            if not target:
                return ToolResult(content="Error: target (search query) required for search scrape", is_error=True)
            return ToolResult(
                content=json.dumps({
                    "url": f"https://hn.algolia.com/?q={quote_plus(target)}",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to search HN for '{target}'",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract matching stories",
                        "Extract: title, URL, points, author, comment count, HN item ID",
                        "Format as JSON array and call store_hackernews_items",
                    ],
                    "extract_fields": ["external_id", "title", "url", "author", "points", "comment_count"],
                }),
            )
        elif scrape_type == "account":
            if not target:
                return ToolResult(content="Error: target (username) required for account scrape", is_error=True)
            return ToolResult(
                content=json.dumps({
                    "url": f"https://news.ycombinator.com/submitted?id={target}",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to go to https://news.ycombinator.com/submitted?id={target}",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract submissions",
                        "Extract: title, URL, points, comment count, HN item ID",
                        "Format as JSON array and call store_hackernews_items",
                    ],
                    "extract_fields": ["external_id", "title", "url", "author", "points", "comment_count"],
                }),
            )
        else:
            return ToolResult(content=f"Error: Unknown scrape type: {scrape_type}", is_error=True)

    @tool(
        name="store_hackernews_items",
        description="Store scraped Hacker News stories as feed items for pipeline processing.",
        parameters={
            "type": "object",
            "properties": {
                "items_json": {
                    "type": "string",
                    "description": "JSON array of scraped stories. Each: {external_id, url, author, title, points, comment_count}",
                },
            },
            "required": ["items_json"],
        },
    )
    def store_hackernews_items(self, items_json: str) -> ToolResult:
        try:
            items = json.loads(items_json)
        except json.JSONDecodeError as e:
            return ToolResult(content=f"Error: Invalid JSON: {e}", is_error=True)

        if not isinstance(items, list):
            return ToolResult(content="Error: Expected a JSON array", is_error=True)

        # Find or create HN source
        sources = self._source_repo.list_by_platform("hackernews")
        if sources:
            source_id = sources[0]["id"]
        else:
            source = self._source_repo.create(
                platform="hackernews",
                source_type="frontpage",
                config={"label": "Hacker News (scraped)"},
            )
            source_id = source["id"]

        # Normalize and store
        batch = []
        for item in items:
            title = item.get("title", "")
            hn_id = item.get("external_id", "")
            url = item.get("url") or (f"https://news.ycombinator.com/item?id={hn_id}" if hn_id else "")
            batch.append({
                "source_id": source_id,
                "platform": "hackernews",
                "external_id": hn_id,
                "author": item.get("author", ""),
                "content": title,
                "url": url,
            })

        result = self._feed_repo.create_batch(batch)

        return ToolResult(
            content=json.dumps({
                "success": True,
                "ingested": result["ingested"],
                "skipped": result["skipped"],
                "source_id": source_id,
                "message": f"Stored {result['ingested']} HN stories ({result['skipped']} duplicates skipped)",
            }),
        )

    @tool(
        name="get_hackernews_sources",
        description="List configured Hacker News sources from the database.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_hackernews_sources(self) -> ToolResult:
        sources = self._source_repo.list_by_platform("hackernews")
        if not sources:
            return ToolResult(content="No Hacker News sources configured.")

        lines = ["Hacker News sources:"]
        for s in sources:
            enabled = "+" if s.get("enabled", True) else "-"
            config = s.get("config", {})
            label = config.get("label") or s["id"][:8]
            lines.append(
                f"  [{enabled}] {s['type']}: {label}"
            )

        return ToolResult(content="\n".join(lines))
