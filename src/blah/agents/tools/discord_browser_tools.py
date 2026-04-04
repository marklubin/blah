"""Browser scraping tools for Discord via MCP router (fallback when API token expires)."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import SourceRepo

logger = logging.getLogger(__name__)

BROWSER_NOTE = (
    "IMPORTANT: Use the MCP router browser tools (mcp__claude_ai_mcp-router__browser_*), "
    "NOT browser-use tools. The router browser has the persistent session."
)


class DiscordBrowserTools:
    """Browser fallback tools for Discord when API token is unavailable."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._source_repo = SourceRepo(db)

    @tool(
        name="check_discord_auth",
        description="Get instructions for checking Discord authentication status in the browser.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def check_discord_auth(self) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "instructions": [
                    "Use mcp__claude_ai_mcp-router__browser_navigate to go to https://discord.com/channels/@me",
                    "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract page content",
                    "Look for auth indicators:",
                    "  - Logged in: server list, channel list, 'Direct Messages'",
                    "  - Logged out: 'Login' button, login form, 'Welcome back!'",
                    "Report the auth status back",
                ],
                "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                "note": BROWSER_NOTE,
                "url": "https://discord.com/channels/@me",
                "logged_in_indicators": ["Direct Messages", "Friends", "Nitro"],
                "logged_out_indicators": ["Login", "Welcome back!", "Log In"],
            }),
        )

    @tool(
        name="get_discord_scrape_instructions",
        description="Get instructions for scraping a Discord channel via browser (fallback when API unavailable).",
        parameters={
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "The Discord server/guild ID",
                },
                "channel_id": {
                    "type": "string",
                    "description": "The Discord channel ID",
                },
            },
            "required": ["server_id", "channel_id"],
        },
    )
    def get_discord_scrape_instructions(self, server_id: str, channel_id: str) -> ToolResult:
        url = f"https://discord.com/channels/{server_id}/{channel_id}"
        return ToolResult(
            content=json.dumps({
                "url": url,
                "browser_tools": "mcp__claude_ai_mcp-router__browser_*",
                "note": BROWSER_NOTE,
                "instructions": [
                    f"Use mcp__claude_ai_mcp-router__browser_navigate to go to {url}",
                    "Use mcp__claude_ai_mcp-router__browser_get_rendered_content to extract messages",
                    "Scroll up to load older messages if needed",
                    "Extract message data: author, text, timestamp, reactions",
                    "Format as JSON array and call store_discord_items (from Discord API tools)",
                ],
                "extract_fields": ["external_id", "author", "text", "url", "created_at", "reaction_count"],
                "note_storage": "Use the existing store_discord_items tool to store scraped messages.",
            }),
        )
