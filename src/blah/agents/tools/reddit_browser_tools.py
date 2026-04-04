"""Browser scraping tools for Reddit via MCP router."""

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


class RedditBrowserTools:
    """Tools for Reddit browser scraping and data ingestion."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)

    @tool(
        name="check_reddit_auth",
        description="Get instructions for checking Reddit authentication status in the browser.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def check_reddit_auth(self) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "instructions": [
                    "Use mcp__claude_ai_mcp-router__browser_navigate to go to https://www.reddit.com",
                    "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                    "Look for auth indicators:",
                    "  - Logged in: username in top-right, 'Create Post', karma count",
                    "  - Logged out: 'Log In' button, 'Sign Up' button",
                    "Report the auth status back",
                ],
                "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                "note": BROWSER_NOTE,
                "url": "https://www.reddit.com",
                "logged_in_indicators": ["Create Post", "karma", "u/"],
                "logged_out_indicators": ["Log In", "Sign Up"],
            }),
        )

    @tool(
        name="get_reddit_scrape_instructions",
        description="Get instructions for scraping a specific Reddit source type.",
        parameters={
            "type": "object",
            "properties": {
                "scrape_type": {
                    "type": "string",
                    "description": "Type of scrape: 'subreddit', 'search', or 'account'",
                    "enum": ["subreddit", "search", "account"],
                },
                "target": {
                    "type": "string",
                    "description": "For subreddit: subreddit name. For search: query. For account: username.",
                },
            },
            "required": ["scrape_type", "target"],
        },
    )
    def get_reddit_scrape_instructions(self, scrape_type: str, target: str) -> ToolResult:
        if not target:
            return ToolResult(content="Error: target is required", is_error=True)

        if scrape_type == "subreddit":
            return ToolResult(
                content=json.dumps({
                    "url": f"https://www.reddit.com/r/{target}/",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to go to https://www.reddit.com/r/{target}/",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                        "Scroll down with mcp__claude_ai_mcp-router__browser_evaluate (window.scrollBy) to load more posts",
                        "Extract post data: title, author, score, comment count, post URL, time posted",
                        "Format as JSON array and call store_reddit_items",
                    ],
                    "extract_fields": ["external_id", "title", "author", "url", "score", "comment_count", "text"],
                }),
            )
        elif scrape_type == "search":
            return ToolResult(
                content=json.dumps({
                    "url": f"https://www.reddit.com/search/?q={quote_plus(target)}",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to search Reddit for '{target}'",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract matching posts",
                        "Extract post data: title, author, score, comment count, subreddit, post URL",
                        "Format as JSON array and call store_reddit_items",
                    ],
                    "extract_fields": ["external_id", "title", "author", "url", "score", "comment_count", "text"],
                }),
            )
        elif scrape_type == "account":
            return ToolResult(
                content=json.dumps({
                    "url": f"https://www.reddit.com/user/{target}/",
                    "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                    "note": BROWSER_NOTE,
                    "instructions": [
                        f"Use mcp__claude_ai_mcp-router__browser_navigate to go to https://www.reddit.com/user/{target}/",
                        "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract user's posts",
                        "Extract post data: title, text, score, comment count, subreddit, post URL",
                        "Format as JSON array and call store_reddit_items",
                    ],
                    "extract_fields": ["external_id", "title", "author", "url", "score", "comment_count", "text"],
                }),
            )
        else:
            return ToolResult(content=f"Error: Unknown scrape type: {scrape_type}", is_error=True)

    @tool(
        name="store_reddit_items",
        description="Store scraped Reddit posts as feed items for pipeline processing.",
        parameters={
            "type": "object",
            "properties": {
                "items_json": {
                    "type": "string",
                    "description": "JSON array of scraped posts. Each post: {external_id, url, author, title, text, score, comment_count}",
                },
            },
            "required": ["items_json"],
        },
    )
    def store_reddit_items(self, items_json: str) -> ToolResult:
        try:
            items = json.loads(items_json)
        except json.JSONDecodeError as e:
            return ToolResult(content=f"Error: Invalid JSON: {e}", is_error=True)

        if not isinstance(items, list):
            return ToolResult(content="Error: Expected a JSON array", is_error=True)

        # Find or create Reddit source
        sources = self._source_repo.list_by_platform("reddit")
        if sources:
            source_id = sources[0]["id"]
        else:
            source = self._source_repo.create(
                platform="reddit",
                source_type="feed",
                config={"label": "Reddit feed (scraped)"},
            )
            source_id = source["id"]

        # Normalize and store
        batch = []
        for item in items:
            title = item.get("title", "")
            text = item.get("text") or item.get("content", "")
            content = f"{title}\n\n{text}".strip() if title and text else title or text
            batch.append({
                "source_id": source_id,
                "platform": "reddit",
                "external_id": item.get("external_id", ""),
                "author": item.get("author", ""),
                "content": content,
                "url": item.get("url", ""),
            })

        result = self._feed_repo.create_batch(batch)

        return ToolResult(
            content=json.dumps({
                "success": True,
                "ingested": result["ingested"],
                "skipped": result["skipped"],
                "source_id": source_id,
                "message": f"Stored {result['ingested']} Reddit posts ({result['skipped']} duplicates skipped)",
            }),
        )

    @tool(
        name="get_reddit_sources",
        description="List configured Reddit sources from the database.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_reddit_sources(self) -> ToolResult:
        sources = self._source_repo.list_by_platform("reddit")
        if not sources:
            return ToolResult(content="No Reddit sources configured.")

        lines = ["Reddit sources:"]
        for s in sources:
            enabled = "+" if s.get("enabled", True) else "-"
            config = s.get("config", {})
            label = config.get("label") or s["id"][:8]
            state = s.get("state", {})
            auth_status = state.get("auth_status", "unknown")
            lines.append(
                f"  [{enabled}] {s['type']}: {label} (auth: {auth_status})"
            )

        return ToolResult(content="\n".join(lines))
