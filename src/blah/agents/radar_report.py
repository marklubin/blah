"""Radar Report Agent — helps review reports and engage via chat."""

from __future__ import annotations

import sqlite3

from blah.adapters.base import PlatformAdapter
from blah.agents.base import BaseAgent
from blah.agents.tools.base import collect_tools
from blah.agents.tools.context_tools import ContextTools
from blah.agents.tools.radar_tools import RadarReportTools
from blah.config.settings import BlahSettings
from blah.db.repository import ReportItemRepo, ReportRepo
from blah.llm.client import LLMClient


class RadarReportAgent(BaseAgent):
    """Agent for reviewing radar reports and engaging."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: sqlite3.Connection,
        settings: BlahSettings,
        adapters: dict[str, PlatformAdapter],
        report_id: str,
    ):
        self._adapters = adapters
        self._report_id = report_id
        self._report_repo = ReportRepo(db)
        self._report_item_repo = ReportItemRepo(db)

        # Create tool instances
        self._report_tools = RadarReportTools(db, adapters, report_id)
        self._context_tools = ContextTools(settings.context_path)

        super().__init__(llm_client, db, settings)

        # Register tools
        for tool_def in collect_tools(self._report_tools):
            self.tool_registry.register(tool_def)
        for tool_def in collect_tools(self._context_tools):
            self.tool_registry.register(tool_def)

    def system_prompt(self) -> str:
        context_md = self._load_context()
        report = self._report_repo.get(self._report_id)
        items = self._report_item_repo.list_by_report(self._report_id)

        report_summary = _format_report_summary(report, items)
        top_items = _format_top_items(items[:5]) if items else "No items yet."

        return f"""# Blah Radar Report Agent

You help review radar reports and engage with relevant signals.

## Your Job
1. Present interesting signals from the report
2. Help the user decide what to engage with
3. Draft replies that match the user's voice
4. Execute engagement (reply, follow) when approved

## User Context
{context_md if context_md else "(No context set yet)"}

## Current Report
{report_summary}

## Top Items
{top_items}

## Workflow
1. Start by showing a summary with list_report_items
2. Use get_item_detail to dive deeper into interesting items
3. For each item, the research phase has already suggested engagement angles
4. Draft replies with draft_reply (this saves a draft for review)
5. Send with send_reply only after user approval
6. Use follow_author to follow interesting people
7. Mark items as reviewed or skipped as you go
8. Use complete_report when done reviewing

## Guidelines
- Present items with their suggested angles — the research is already done
- Match the user's voice from context.md when drafting replies
- Keep replies authentic — don't be promotional or forced
- Respect platform character limits (Bluesky: 300, Twitter: 280)
- Ask before sending — never auto-post
- Use suggest_context_update when you learn new interests or preferences"""


def _format_report_summary(report: dict | None, items: list[dict]) -> str:
    if not report:
        return "Report not found."

    pending = len([i for i in items if i.get("status") == "pending"])
    reviewed = len([i for i in items if i.get("status") == "reviewed"])
    engaged = len([i for i in items if i.get("status") == "engaged"])

    return f"""ID: {report['id'][:8]}
Created: {report.get('created_at', 'unknown')}
Status: {report.get('status', 'pending')}
Items: {len(items)} total ({pending} pending, {reviewed} reviewed, {engaged} engaged)"""


def _format_top_items(items: list[dict]) -> str:
    if not items:
        return "No items."

    lines = []
    for i, item in enumerate(items, 1):
        data = item.get("data", {})
        author = data.get("author", "unknown")
        content = (data.get("content", "")[:60] + "...") if data.get("content") else ""
        score = item.get("relevance_score", 0)
        lines.append(f"{i}. @{author} ({score:.2f}): {content}")

    return "\n".join(lines)
