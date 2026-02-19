"""Tools for Discord via API adapter."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.adapters.base import PlatformAdapter
from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import FeedItemRepo, SourceRepo

logger = logging.getLogger(__name__)


class DiscordTools:
    """Tools for Discord server/channel discovery and data ingestion."""

    def __init__(self, db: sqlite3.Connection, adapter: PlatformAdapter | None = None):
        self._db = db
        self._adapter = adapter
        self._source_repo = SourceRepo(db)
        self._feed_repo = FeedItemRepo(db)

    @tool(
        name="list_discord_servers",
        description="List Discord servers the authenticated user is a member of.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def list_discord_servers(self) -> ToolResult:
        if not self._adapter or not hasattr(self._adapter, "get_guilds"):
            return ToolResult(
                content="Error: Discord adapter not configured. Add discord_token to config.",
                is_error=True,
            )

        try:
            guilds = self._adapter.get_guilds()
            if not guilds:
                return ToolResult(content="No servers found.")

            lines = ["Discord servers:"]
            for g in guilds:
                owner_tag = " (owner)" if g.get("owner") else ""
                lines.append(f"  - {g['name']} (id: {g['id']}){owner_tag}")

            return ToolResult(content="\n".join(lines))
        except Exception:
            logger.exception("Failed to list Discord servers")
            return ToolResult(content="Error: Failed to list servers", is_error=True)

    @tool(
        name="list_discord_channels",
        description="List text channels in a Discord server.",
        parameters={
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "The server/guild ID to list channels for",
                },
            },
            "required": ["server_id"],
        },
    )
    def list_discord_channels(self, server_id: str) -> ToolResult:
        if not self._adapter or not hasattr(self._adapter, "get_guild_channels"):
            return ToolResult(
                content="Error: Discord adapter not configured. Add discord_token to config.",
                is_error=True,
            )

        try:
            channels = self._adapter.get_guild_channels(server_id)
            if not channels:
                return ToolResult(content=f"No text channels found in server {server_id}.")

            lines = [f"Text channels in server {server_id}:"]
            for ch in channels:
                ch_type = "announcement" if ch["type"] == 5 else "text"
                lines.append(f"  - #{ch['name']} (id: {ch['id']}, {ch_type})")

            return ToolResult(content="\n".join(lines))
        except Exception:
            logger.exception("Failed to list channels for server %s", server_id)
            return ToolResult(
                content=f"Error: Failed to list channels for server {server_id}",
                is_error=True,
            )

    @tool(
        name="store_discord_items",
        description="Store Discord messages as feed items for pipeline processing (manual ingestion fallback).",
        parameters={
            "type": "object",
            "properties": {
                "items_json": {
                    "type": "string",
                    "description": "JSON array of messages. Each: {external_id, url, author, text, created_at, reaction_count, channel_name}",
                },
            },
            "required": ["items_json"],
        },
    )
    def store_discord_items(self, items_json: str) -> ToolResult:
        try:
            items = json.loads(items_json)
        except json.JSONDecodeError as e:
            return ToolResult(content=f"Error: Invalid JSON: {e}", is_error=True)

        if not isinstance(items, list):
            return ToolResult(content="Error: Expected a JSON array", is_error=True)

        # Find or create Discord source
        sources = self._source_repo.list_by_platform("discord")
        if sources:
            source_id = sources[0]["id"]
        else:
            source = self._source_repo.create(
                platform="discord",
                source_type="channel",
                config={"label": "Discord channel (manual)"},
            )
            source_id = source["id"]

        # Normalize and store
        batch = []
        for item in items:
            batch.append({
                "source_id": source_id,
                "platform": "discord",
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
                "message": f"Stored {result['ingested']} Discord messages ({result['skipped']} duplicates skipped)",
            }),
        )

    @tool(
        name="get_discord_sources",
        description="List configured Discord sources from the database.",
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    def get_discord_sources(self) -> ToolResult:
        sources = self._source_repo.list_by_platform("discord")
        if not sources:
            return ToolResult(content="No Discord sources configured.")

        lines = ["Discord sources:"]
        for s in sources:
            enabled = "+" if s.get("enabled", True) else "-"
            config = s.get("config", {})
            label = config.get("label") or s["id"][:8]
            channel_id = config.get("channel_id", "")
            extra = f", channel: {channel_id}" if channel_id else ""
            lines.append(
                f"  [{enabled}] {s['type']}: {label}{extra}"
            )

        return ToolResult(content="\n".join(lines))
