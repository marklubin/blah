"""Tools available to the Rant Agent."""

from __future__ import annotations

import json
import sqlite3

from blah.agents.tools.base import ToolResult, tool
from blah.db.repository import PieceRepo, RantRepo


class RantTools:
    """Tool methods for rant creation and editing. Bound to a specific rant."""

    def __init__(self, conn: sqlite3.Connection, rant_id: str):
        self.conn = conn
        self.rant_id = rant_id
        self.rant_repo = RantRepo(conn)
        self.piece_repo = PieceRepo(conn)

    @tool(
        name="set_title",
        description="Set or update the rant title.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The rant title"},
            },
            "required": ["title"],
        },
    )
    def set_title(self, title: str) -> ToolResult:
        rant = self.rant_repo.update(self.rant_id, title=title)
        if rant is None:
            return ToolResult(content=json.dumps({"error": "Rant not found"}), is_error=True)
        return ToolResult(content=json.dumps({"title": rant["title"]}))

    @tool(
        name="set_summary",
        description="Set or update the rant summary — a brief description of the topic and angle.",
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "The rant summary"},
            },
            "required": ["summary"],
        },
    )
    def set_summary(self, summary: str) -> ToolResult:
        rant = self.rant_repo.update(self.rant_id, summary=summary)
        if rant is None:
            return ToolResult(content=json.dumps({"error": "Rant not found"}), is_error=True)
        return ToolResult(content=json.dumps({"summary": rant["summary"]}))

    @tool(
        name="create_piece",
        description=(
            "Create a platform-specific piece of content for this rant. "
            "Supported platforms: bluesky, twitter."
        ),
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Target platform (bluesky, twitter)",
                    "enum": ["bluesky", "twitter"],
                },
                "content": {
                    "type": "string",
                    "description": "The content text for this platform",
                },
                "target": {
                    "type": "object",
                    "description": "Platform-specific parameters (optional)",
                },
            },
            "required": ["platform", "content"],
        },
    )
    def create_piece(
        self,
        platform: str,
        content: str,
        target: dict | None = None,
    ) -> ToolResult:
        piece = self.piece_repo.create(
            rant_id=self.rant_id,
            platform=platform,
            content=content,
            target=target,
        )
        return ToolResult(
            content=json.dumps({
                "piece_id": piece["id"],
                "platform": piece["platform"],
                "status": piece["status"],
            })
        )

    @tool(
        name="update_piece",
        description="Update the content of an existing piece.",
        parameters={
            "type": "object",
            "properties": {
                "piece_id": {"type": "string", "description": "The piece ID to update"},
                "content": {"type": "string", "description": "The new content"},
            },
            "required": ["piece_id", "content"],
        },
    )
    def update_piece(self, piece_id: str, content: str) -> ToolResult:
        piece = self.piece_repo.get(piece_id)
        if piece is None:
            return ToolResult(content=json.dumps({"error": "Piece not found"}), is_error=True)
        if piece["rant_id"] != self.rant_id:
            return ToolResult(
                content=json.dumps({"error": "Piece does not belong to this rant"}),
                is_error=True,
            )
        updated = self.piece_repo.update(piece_id, content=content)
        return ToolResult(
            content=json.dumps({
                "piece_id": updated["id"],
                "platform": updated["platform"],
                "content": updated["content"],
            })
        )

    @tool(
        name="finalize_rant",
        description=(
            "Mark the rant as active and all draft pieces as approved. "
            "Call this when the user is happy with the rant and ready to publish."
        ),
        parameters={"type": "object", "properties": {}},
    )
    def finalize_rant(self) -> ToolResult:
        rant = self.rant_repo.get(self.rant_id)
        if rant is None:
            return ToolResult(content=json.dumps({"error": "Rant not found"}), is_error=True)

        self.rant_repo.update(self.rant_id, status="active")

        pieces = self.piece_repo.list_by_rant(self.rant_id)
        approved_count = 0
        for piece in pieces:
            if piece["status"] == "draft":
                self.piece_repo.update(piece["id"], status="approved")
                approved_count += 1

        return ToolResult(
            content=json.dumps({
                "status": "active",
                "pieces_approved": approved_count,
                "total_pieces": len(pieces),
            })
        )

    @tool(
        name="attach_resource",
        description="Attach a resource (image, video, doc, or URL) to the rant.",
        parameters={
            "type": "object",
            "properties": {
                "path_or_url": {
                    "type": "string",
                    "description": "File path or URL of the resource",
                },
                "resource_type": {
                    "type": "string",
                    "description": "Type of resource",
                    "enum": ["image", "video", "doc", "url"],
                },
            },
            "required": ["path_or_url", "resource_type"],
        },
    )
    def attach_resource(self, path_or_url: str, resource_type: str) -> ToolResult:
        # Simple implementation: just record it in the resources table
        from blah.db.repository import _new_id

        resource_id = _new_id()
        self.conn.execute(
            "INSERT INTO resources (id, type, location) VALUES (?, ?, ?)",
            (resource_id, resource_type, path_or_url),
        )
        self.conn.execute(
            "INSERT INTO rant_resources (rant_id, resource_id) VALUES (?, ?)",
            (self.rant_id, resource_id),
        )
        self.conn.commit()
        return ToolResult(
            content=json.dumps({
                "resource_id": resource_id,
                "type": resource_type,
                "location": path_or_url,
            })
        )
