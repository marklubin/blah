"""Rant Agent — helps create and refine rants via chat."""

from __future__ import annotations

import sqlite3

from blah.agents.base import BaseAgent
from blah.agents.tools.base import collect_tools
from blah.agents.tools.context_tools import ContextTools
from blah.agents.tools.publish_tools import PublishTools
from blah.agents.tools.rant_tools import RantTools
from blah.agents.tools.suggestion_tools import SuggestionTools
from blah.agents.tools.web_tools import WebTools
from blah.config.settings import BlahSettings
from blah.db.repository import PieceRepo, RantRepo
from blah.llm.client import LLMClient


class RantAgent(BaseAgent):
    """Agent for creating and refining rants."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: sqlite3.Connection,
        settings: BlahSettings,
        rant_id: str,
    ):
        self.rant_id = rant_id
        self.rant_repo = RantRepo(db)
        self.piece_repo = PieceRepo(db)

        # Create tool instances and register their tools
        self._rant_tools = RantTools(db, rant_id)
        self._context_tools = ContextTools(settings.context_path)
        self._publish_tools = PublishTools(db, settings, rant_id)
        self._suggestion_tools = SuggestionTools(db, rant_id)
        self._web_tools = WebTools()

        # Must call super().__init__ after setting up tool instances
        # because it calls collect_tools(self) — but we use external tool objects
        super().__init__(llm_client, db, settings)

        # Register tools from the external tool objects
        for tool_def in collect_tools(self._rant_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._context_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._publish_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._suggestion_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._web_tools):
            self.tool_registry.register(tool_def)

    def system_prompt(self) -> str:
        context_md = self._load_context()
        rant = self.rant_repo.get(self.rant_id)
        pieces = self.piece_repo.list_by_rant(self.rant_id)

        if rant and (rant.get("title") or rant.get("summary") or pieces):
            rant_state = _format_rant_state(rant, pieces)
        else:
            rant_state = "New rant — nothing yet."

        return f"""# Blah Rant Agent

You help create and refine rants — content for posting across platforms.

## Your Job
1. Understand what the user wants to make noise about
2. Help refine the angle/positioning
3. Draft platform-specific pieces (bluesky, twitter)
4. Finalize when ready

## User Context
{context_md if context_md else "(No context set yet)"}

## Current Rant
{rant_state}

## Guidelines
- Match the user's voice (see context)
- Keep pieces platform-appropriate:
  - Bluesky: conversational, can be longer
  - Twitter: punchy, thread-friendly, 280 char limit per post
- Ask clarifying questions before drafting
- Use set_title and set_summary to structure the rant before creating pieces
- Use create_piece to draft content for each platform
- Use list_pieces to show all drafted content with full text and char counts
- Use finalize_rant when the user is satisfied and ready to publish
- Use publish_rant to post approved pieces to platforms (the user can say "post it")
- Use web_search and fetch_url to research topics and gather context
- Use list_suggestions to check for queued suggestions the user may want to turn into rants
- Use convert_suggestion to mark a suggestion as used, or dismiss_suggestion to skip it
- Use suggest_context_update when you learn something about the user's preferences"""


def _format_rant_state(rant: dict, pieces: list[dict]) -> str:
    lines = []
    lines.append(f"**Title:** {rant.get('title') or '(not set)'}")
    lines.append(f"**Summary:** {rant.get('summary') or '(not set)'}")
    lines.append(f"**Status:** {rant.get('status', 'draft')}")

    if pieces:
        lines.append(f"\n**Pieces ({len(pieces)}):**")
        for p in pieces:
            content_preview = p["content"][:80] + "..." if len(p["content"]) > 80 else p["content"]
            lines.append(f"- [{p['platform']}] ({p['status']}) {content_preview}")
    else:
        lines.append("\nNo pieces yet.")

    return "\n".join(lines)
