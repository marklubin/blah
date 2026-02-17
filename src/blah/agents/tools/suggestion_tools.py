"""Tools for browsing and managing rant suggestions."""

from __future__ import annotations

import json
import logging
import sqlite3

from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import SuggestionRepo

logger = logging.getLogger(__name__)


class SuggestionTools:
    """Tool methods for browsing and acting on suggestions."""

    def __init__(self, conn: sqlite3.Connection, rant_id: str):
        self.conn = conn
        self.rant_id = rant_id
        self.repo = SuggestionRepo(conn)
        logger.debug("SuggestionTools initialized for rant: %s", rant_id)

    @tool(
        name="list_suggestions",
        description="List rant suggestions, optionally filtered by status.",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status (queued, reviewed, converted, dismissed)",
                    "enum": ["queued", "reviewed", "converted", "dismissed"],
                },
            },
        },
    )
    def list_suggestions(self, status: str = "queued") -> ToolResult:
        suggestions = self.repo.list_by_status(status)
        items = []
        for s in suggestions:
            items.append({
                "id": s["id"],
                "idea": s["idea"],
                "source": s.get("source", "api"),
                "tags": s.get("tags", []),
                "status": s["status"],
                "created_at": s.get("created_at"),
            })
        return ToolResult(
            content=json.dumps({"suggestions": items, "total": len(items)})
        )

    @tool(
        name="get_suggestion",
        description="Get full details of a suggestion.",
        parameters={
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "The suggestion ID",
                },
            },
            "required": ["suggestion_id"],
        },
    )
    def get_suggestion(self, suggestion_id: str) -> ToolResult:
        s = self.repo.get(suggestion_id)
        if s is None:
            return ToolResult(
                content=json.dumps({"error": "Suggestion not found"}),
                is_error=True,
            )
        return ToolResult(content=json.dumps(s))

    @tool(
        name="convert_suggestion",
        description="Mark a suggestion as converted to a rant. Links it to the current rant.",
        parameters={
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "The suggestion ID to convert",
                },
            },
            "required": ["suggestion_id"],
        },
    )
    def convert_suggestion(self, suggestion_id: str) -> ToolResult:
        s = self.repo.get(suggestion_id)
        if s is None:
            return ToolResult(
                content=json.dumps({"error": "Suggestion not found"}),
                is_error=True,
            )
        updated = self.repo.update(
            suggestion_id,
            status="converted",
            rant_id=self.rant_id,
            reviewed_at=__import__("datetime").datetime.now().isoformat(),
        )
        return ToolResult(
            content=json.dumps({
                "id": updated["id"],
                "status": updated["status"],
                "rant_id": updated.get("rant_id"),
            })
        )

    @tool(
        name="dismiss_suggestion",
        description="Dismiss a suggestion so it no longer appears in the queued list.",
        parameters={
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "The suggestion ID to dismiss",
                },
            },
            "required": ["suggestion_id"],
        },
    )
    def dismiss_suggestion(self, suggestion_id: str) -> ToolResult:
        s = self.repo.get(suggestion_id)
        if s is None:
            return ToolResult(
                content=json.dumps({"error": "Suggestion not found"}),
                is_error=True,
            )
        updated = self.repo.update(
            suggestion_id,
            status="dismissed",
            reviewed_at=__import__("datetime").datetime.now().isoformat(),
        )
        return ToolResult(
            content=json.dumps({"id": updated["id"], "status": updated["status"]})
        )
