"""Context tools — shared across all agents."""

from __future__ import annotations

import json
from pathlib import Path

from blah.agents.tools.base import ToolResult, tool


class ContextTools:
    """Tool methods for context.md management.

    Phase 2: simple append. Phase 5 replaces this with Context Manager Agent.
    """

    def __init__(self, context_path: Path):
        self.context_path = context_path

    @tool(
        name="suggest_context_update",
        description=(
            "Suggest an update to the shared context (context.md). "
            "Use this when you learn something about the user's preferences, "
            "voice, interests, or important notes that should persist across sessions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "suggestion": {
                    "type": "string",
                    "description": "The context update to add",
                },
            },
            "required": ["suggestion"],
        },
    )
    def suggest_context_update(self, suggestion: str) -> ToolResult:
        try:
            current = ""
            if self.context_path.exists():
                current = self.context_path.read_text()

            # Simple append under Notes section for now
            if "## Notes" in current:
                current = current.rstrip() + f"\n- {suggestion}\n"
            else:
                current = current.rstrip() + f"\n\n## Notes\n- {suggestion}\n"

            self.context_path.write_text(current)
            return ToolResult(
                content=json.dumps({"success": True, "summary": f"Added to context: {suggestion}"})
            )
        except Exception as e:
            return ToolResult(content=json.dumps({"error": str(e)}), is_error=True)
