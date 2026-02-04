"""Database repositories for CRUD operations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class RantRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, title: str | None = None, summary: str | None = None) -> dict:
        rant_id = _new_id()
        self.conn.execute(
            "INSERT INTO rants (id, title, summary, status) VALUES (?, ?, ?, ?)",
            (rant_id, title, summary, "draft"),
        )
        self.conn.commit()
        return self.get(rant_id)

    def get(self, rant_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM rants WHERE id = ?", (rant_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM rants ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, rant_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(rant_id)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [rant_id]
        self.conn.execute(
            f"UPDATE rants SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(rant_id)

    def delete(self, rant_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM rants WHERE id = ?", (rant_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM rants").fetchone()
        return row["cnt"]


class PieceRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        rant_id: str,
        platform: str,
        content: str,
        target: dict | None = None,
        scheduled_at: datetime | None = None,
    ) -> dict:
        piece_id = _new_id()
        self.conn.execute(
            "INSERT INTO pieces (id, rant_id, platform, content, target, scheduled_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                piece_id,
                rant_id,
                platform,
                content,
                json.dumps(target) if target else None,
                scheduled_at.isoformat() if scheduled_at else None,
                "draft",
            ),
        )
        self.conn.commit()
        return self.get(piece_id)

    def get(self, piece_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("target"):
            result["target"] = json.loads(result["target"])
        if result.get("manual_override"):
            result["manual_override"] = json.loads(result["manual_override"])
        return result

    def list_by_rant(self, rant_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM pieces WHERE rant_id = ?", (rant_id,)
        ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if r.get("target"):
                r["target"] = json.loads(r["target"])
            if r.get("manual_override"):
                r["manual_override"] = json.loads(r["manual_override"])
            results.append(r)
        return results

    def update(self, piece_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(piece_id)
        if "target" in fields and isinstance(fields["target"], dict):
            fields["target"] = json.dumps(fields["target"])
        if "manual_override" in fields and isinstance(fields["manual_override"], dict):
            fields["manual_override"] = json.dumps(fields["manual_override"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [piece_id]
        self.conn.execute(
            f"UPDATE pieces SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(piece_id)

    def list_failed(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM pieces WHERE status = 'failed'"
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM pieces").fetchone()
        return row["cnt"]


class ChatHistoryRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, chat_key: str) -> list[dict]:
        row = self.conn.execute(
            "SELECT messages FROM chat_histories WHERE id = ?", (chat_key,)
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["messages"])

    def save(self, chat_key: str, messages: list[dict]) -> None:
        self.conn.execute(
            "INSERT INTO chat_histories (id, messages) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET messages = excluded.messages",
            (chat_key, json.dumps(messages)),
        )
        self.conn.commit()


# Stubs for radar repos (Phase 4)
class SourceRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM sources").fetchone()
        return row["cnt"]


class FeedItemRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn


class ReportRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM reports").fetchone()
        return row["cnt"]


class ReportItemRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
