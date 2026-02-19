"""Radar Config Agent — helps configure radar sources via chat."""

from __future__ import annotations

import sqlite3

from blah.adapters.base import PlatformAdapter
from blah.agents.base import BaseAgent
from blah.agents.tools.base import collect_tools
from blah.agents.tools.context_tools import ContextTools
from blah.agents.tools.discord_tools import DiscordTools
from blah.agents.tools.linkedin_tools import LinkedInTools
from blah.agents.tools.radar_tools import RadarConfigTools
from blah.agents.tools.web_tools import WebTools
from blah.config.settings import BlahSettings
from blah.db.repository import SourceRepo
from blah.llm.client import LLMClient


class RadarConfigAgent(BaseAgent):
    """Agent for configuring radar sources."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: sqlite3.Connection,
        settings: BlahSettings,
        adapters: dict[str, PlatformAdapter],
    ):
        self._adapters = adapters
        self._source_repo = SourceRepo(db)

        # Create tool instances
        self._config_tools = RadarConfigTools(db, adapters)
        self._context_tools = ContextTools(settings.context_path)
        self._web_tools = WebTools()
        self._linkedin_tools = LinkedInTools(db)
        self._discord_tools = DiscordTools(db, adapter=adapters.get("discord"))

        super().__init__(llm_client, db, settings)

        # Register tools
        for tool_def in collect_tools(self._config_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._context_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._web_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._linkedin_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._discord_tools):
            self.tool_registry.register(tool_def)

    def system_prompt(self) -> str:
        context_md = self._load_context()
        sources = self._source_repo.list_all()
        available_platforms = list(self._adapters.keys())
        # LinkedIn is always available (browser-based, no adapter needed)
        if "linkedin" not in available_platforms:
            available_platforms.append("linkedin")

        source_state = _format_sources(sources) if sources else "No sources configured yet."

        return f"""# Blah Radar Config Agent

You help configure what feeds and accounts to monitor for relevant signals.

## Your Job
1. Understand what topics, people, or conversations the user wants to track
2. Help set up appropriate sources (accounts, timelines, searches)
3. Explain what each source will capture
4. Help tune the configuration over time

## User Context
{context_md if context_md else "(No context set yet)"}

## Available Platforms
{', '.join(available_platforms) if available_platforms else "None configured"}

## Current Sources
{source_state}

## Source Types
- **account**: Follow a specific user's posts (requires handle) — Bluesky, Twitter, Reddit
- **timeline**: Monitor your home feed — Bluesky, Twitter, Reddit
- **search**: Track posts matching a keyword/phrase — all platforms
- **subreddit**: Monitor a specific subreddit — Reddit only
- **feed**: Monitor home feed — LinkedIn only (requires browser scraping)
- **profile**: Monitor a specific person's activity — LinkedIn only
- **channel**: Monitor a specific channel's messages — Discord and Telegram

## Platform Notes
- **Bluesky/Twitter**: Polled automatically via API when you run `blah radar pull`
- **Reddit**: Polled automatically via API. Subreddit sources use `get_subreddit_feed`
- **LinkedIn**: No public API. Sources are scraped via browser by Claude, then ingested.
  Use `check_linkedin_auth` to verify browser session, `get_scrape_instructions` for scraping guides,
  and `store_linkedin_items` to save scraped data. Then `blah radar pull --skip-poll` processes them.
  **IMPORTANT**: Always use the MCP router browser tools (`mcp__claude_ai_router__browser_*`) for LinkedIn —
  NOT the `browser-use` tools. The router browser has the persistent logged-in LinkedIn session.
- **Telegram**: Polled automatically via API. Uses Telethon with a StringSession.
  Run `python scripts/telegram_auth.py` to generate a session string.
  Channel sources use `get_channel_messages`. Channel username goes in `channel_id` field.
- **Discord**: Polled automatically via API using a user token. Use `list_discord_servers` and
  `list_discord_channels` to discover servers/channels, then add channel sources.
  `store_discord_items` is available as a manual ingestion fallback if needed.

## Discovery Tools
- **web_search**: Search the web to find interesting people/topics
- **search_posts**: Search posts on a platform to find relevant accounts
- **get_profile**: Look up a user's profile before adding them
- **get_recent_posts**: Preview someone's content before adding

## LinkedIn Tools
- **check_linkedin_auth**: Check if LinkedIn browser session is active
- **get_scrape_instructions**: Get step-by-step scraping instructions for feed/profile/search
- **store_linkedin_items**: Store scraped LinkedIn posts for pipeline processing
- **get_linkedin_sources**: List configured LinkedIn sources

## Discord Tools
- **list_discord_servers**: List Discord servers the user is a member of
- **list_discord_channels**: List channels in a Discord server
- **store_discord_items**: Store Discord messages manually (fallback)
- **get_discord_sources**: List configured Discord sources

## Guidelines
- Start by understanding what the user wants to track
- Use web_search to find interesting people in their areas of interest
- Use search_posts to discover relevant accounts on platforms
- Use get_profile and get_recent_posts to vet accounts before adding
- Don't add too many sources at once — quality over quantity
- Explain what each source will capture
- Use suggest_context_update when you learn new interests or preferences
- For Bluesky handles, use the full format: username.bsky.social
- For Reddit, suggest subreddit sources for topic monitoring
- For LinkedIn, explain that sources need browser scraping (no API)
- For Discord, use list_discord_servers/list_discord_channels to help pick channels"""


def _format_sources(sources: list[dict]) -> str:
    lines = []
    for s in sources:
        enabled = "✓" if s.get("enabled", True) else "✗"
        config = s.get("config", {})
        label = config.get("label") or s.get("id")[:8]
        lines.append(f"[{enabled}] {s['platform']}/{s['type']}: {label}")
    return "\n".join(lines)
