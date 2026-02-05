"""Radar Config Agent — helps configure radar sources via chat."""

from __future__ import annotations

import sqlite3

from blah.adapters.base import PlatformAdapter
from blah.agents.base import BaseAgent
from blah.agents.tools.base import collect_tools
from blah.agents.tools.context_tools import ContextTools
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

        super().__init__(llm_client, db, settings)

        # Register tools
        for tool_def in collect_tools(self._config_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._context_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._web_tools):
            self.tool_registry.register(tool_def)

    def system_prompt(self) -> str:
        context_md = self._load_context()
        sources = self._source_repo.list_all()
        available_platforms = list(self._adapters.keys())

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
- **account**: Follow a specific user's posts (requires handle)
- **timeline**: Monitor your home feed
- **search**: Track posts matching a keyword/phrase (requires query)

## Discovery Tools
- **web_search**: Search the web to find interesting people/topics
- **search_posts**: Search posts on a platform to find relevant accounts
- **get_profile**: Look up a user's profile before adding them
- **get_recent_posts**: Preview someone's content before adding

## Guidelines
- Start by understanding what the user wants to track
- Use web_search to find interesting people in their areas of interest
- Use search_posts to discover relevant accounts on platforms
- Use get_profile and get_recent_posts to vet accounts before adding
- Don't add too many sources at once — quality over quantity
- Explain what each source will capture
- Use suggest_context_update when you learn new interests or preferences
- For Bluesky handles, use the full format: username.bsky.social"""


def _format_sources(sources: list[dict]) -> str:
    lines = []
    for s in sources:
        enabled = "✓" if s.get("enabled", True) else "✗"
        config = s.get("config", {})
        label = config.get("label") or s.get("id")[:8]
        lines.append(f"[{enabled}] {s['platform']}/{s['type']}: {label}")
    return "\n".join(lines)
