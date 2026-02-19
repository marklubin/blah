"""Database repositories for CRUD operations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ─────────────────────────────────────────────────────────────────
# Suggestion queue
# ─────────────────────────────────────────────────────────────────


class SuggestionRepo:
    """Repository for rant suggestions pulled from the cloud queue."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self, idea: str, source: str = "api", tags: list[str] | None = None
    ) -> dict:
        suggestion_id = _new_id()
        self.conn.execute(
            "INSERT INTO suggestions (id, idea, source, tags) VALUES (?, ?, ?, ?)",
            (suggestion_id, idea, source, json.dumps(tags or [])),
        )
        self.conn.commit()
        return self.get(suggestion_id)

    def get(self, suggestion_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_status(self, status: str = "queued") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM suggestions WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM suggestions ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, suggestion_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(suggestion_id)
        if "tags" in fields and isinstance(fields["tags"], list):
            fields["tags"] = json.dumps(fields["tags"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [suggestion_id]
        self.conn.execute(
            f"UPDATE suggestions SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(suggestion_id)

    def delete(self, suggestion_id: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM suggestions WHERE id = ?", (suggestion_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self, status: str | None = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM suggestions WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM suggestions"
            ).fetchone()
        return row["cnt"]

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("tags"):
            result["tags"] = json.loads(result["tags"])
        return result


# ─────────────────────────────────────────────────────────────────
# Rant flow
# ─────────────────────────────────────────────────────────────────


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

    def list_published(self) -> list[dict]:
        """List pieces that have been published (have an external_id)."""
        rows = self.conn.execute(
            "SELECT * FROM pieces WHERE status = 'published' AND external_id IS NOT NULL"
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


# ─────────────────────────────────────────────────────────────────
# Radar repositories
# ─────────────────────────────────────────────────────────────────


class SourceRepo:
    """Repository for radar sources (accounts, feeds to monitor)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        platform: str,
        source_type: str,
        config: dict,
        enabled: bool = True,
    ) -> dict:
        source_id = _new_id()
        self.conn.execute(
            "INSERT INTO sources (id, platform, type, config, state, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, platform, source_type, json.dumps(config), "{}", enabled),
        )
        self.conn.commit()
        return self.get(source_id)

    def get(self, source_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_all(self, enabled_only: bool = False) -> list[dict]:
        if enabled_only:
            rows = self.conn.execute(
                "SELECT * FROM sources WHERE enabled = 1"
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM sources").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_by_platform(self, platform: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE platform = ? AND enabled = 1",
            (platform,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, source_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(source_id)
        if "config" in fields and isinstance(fields["config"], dict):
            fields["config"] = json.dumps(fields["config"])
        if "state" in fields and isinstance(fields["state"], dict):
            fields["state"] = json.dumps(fields["state"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [source_id]
        self.conn.execute(
            f"UPDATE sources SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(source_id)

    def delete(self, source_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM sources").fetchone()
        return row["cnt"]

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("config"):
            result["config"] = json.loads(result["config"])
        if result.get("state"):
            result["state"] = json.loads(result["state"])
        return result


class FeedItemRepo:
    """Repository for feed items (posts fetched from sources)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        source_id: str,
        platform: str,
        external_id: str,
        author: str,
        content: str,
        url: str | None = None,
    ) -> dict:
        item_id = _new_id()
        self.conn.execute(
            "INSERT INTO feed_items "
            "(id, source_id, platform, external_id, url, author, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, source_id, platform, external_id, url, author, content, "raw"),
        )
        self.conn.commit()
        return self.get(item_id)

    def get(self, item_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM feed_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_by_external_id(self, platform: str, external_id: str) -> dict | None:
        """Check if we already have this item (deduplication)."""
        row = self.conn.execute(
            "SELECT * FROM feed_items WHERE platform = ? AND external_id = ?",
            (platform, external_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_status(self, status: str, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feed_items WHERE status = ? "
            "ORDER BY fetched_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_by_source(self, source_id: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feed_items WHERE source_id = ? "
            "ORDER BY fetched_at DESC LIMIT ?",
            (source_id, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_by_report(self, report_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feed_items WHERE report_id = ? "
            "ORDER BY relevance_score DESC",
            (report_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, item_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(item_id)
        if "enrichment" in fields and isinstance(fields["enrichment"], dict):
            fields["enrichment"] = json.dumps(fields["enrichment"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [item_id]
        self.conn.execute(
            f"UPDATE feed_items SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(item_id)

    def count(self, status: str | None = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM feed_items WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM feed_items"
            ).fetchone()
        return row["cnt"]

    def create_batch(self, items: list[dict]) -> dict:
        """Bulk insert feed items with deduplication.

        Each item dict should have: source_id, platform, external_id, author, content, url

        Returns:
            dict with "ingested" count and "skipped" count
        """
        ingested = 0
        skipped = 0
        for item in items:
            external_id = item.get("external_id")
            platform = item.get("platform", "linkedin")
            if not external_id:
                skipped += 1
                continue
            # Check for duplicate
            existing = self.get_by_external_id(platform, external_id)
            if existing:
                skipped += 1
                continue
            self.create(
                source_id=item.get("source_id", ""),
                platform=platform,
                external_id=external_id,
                author=item.get("author", ""),
                content=item.get("content") or item.get("text", ""),
                url=item.get("url"),
            )
            ingested += 1
        return {"ingested": ingested, "skipped": skipped}

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("enrichment"):
            result["enrichment"] = json.loads(result["enrichment"])
        return result


class ReportRepo:
    """Repository for radar reports."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, sources_polled: list[str] | None = None) -> dict:
        report_id = _new_id()
        self.conn.execute(
            "INSERT INTO reports (id, status, sources_polled) VALUES (?, ?, ?)",
            (report_id, "pending", json.dumps(sources_polled or [])),
        )
        self.conn.commit()
        return self.get(report_id)

    def get(self, report_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def get_latest_pending(self) -> dict | None:
        """Get the oldest pending report for review."""
        row = self.conn.execute(
            "SELECT * FROM reports WHERE status = 'pending' "
            "ORDER BY generated_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_all(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM reports ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, report_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(report_id)
        if "sources_polled" in fields and isinstance(fields["sources_polled"], list):
            fields["sources_polled"] = json.dumps(fields["sources_polled"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [report_id]
        self.conn.execute(
            f"UPDATE reports SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(report_id)

    def count(self, status: str | None = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM reports WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM reports"
            ).fetchone()
        return row["cnt"]

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("sources_polled"):
            result["sources_polled"] = json.loads(result["sources_polled"])
        return result


class ReportItemRepo:
    """Repository for report items (signals, follows, trends)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        report_id: str,
        item_type: str,
        data: dict,
        relevance_score: float | None = None,
    ) -> dict:
        item_id = _new_id()
        self.conn.execute(
            "INSERT INTO report_items (id, report_id, type, data, relevance_score, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, report_id, item_type, json.dumps(data), relevance_score, "new"),
        )
        self.conn.commit()
        return self.get(item_id)

    def get(self, item_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM report_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_report(self, report_id: str, status: str | None = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM report_items WHERE report_id = ? AND status = ? "
                "ORDER BY relevance_score DESC",
                (report_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM report_items WHERE report_id = ? "
                "ORDER BY relevance_score DESC",
                (report_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, item_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(item_id)
        if "data" in fields and isinstance(fields["data"], dict):
            fields["data"] = json.dumps(fields["data"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [item_id]
        self.conn.execute(
            f"UPDATE report_items SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        self.conn.commit()
        return self.get(item_id)

    def count_by_report(self, report_id: str, status: str | None = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM report_items "
                "WHERE report_id = ? AND status = ?",
                (report_id, status),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM report_items WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        return row["cnt"]

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("data"):
            result["data"] = json.loads(result["data"])
        return result


# ─────────────────────────────────────────────────────────────────
# Piece metrics
# ─────────────────────────────────────────────────────────────────


class PieceMetricsRepo:
    """Repository for piece engagement metrics snapshots."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        piece_id: str,
        platform: str,
        like_count: int = 0,
        repost_count: int = 0,
        reply_count: int = 0,
        raw_data: dict | None = None,
    ) -> dict:
        metric_id = _new_id()
        self.conn.execute(
            "INSERT INTO piece_metrics (id, piece_id, platform, like_count, repost_count, reply_count, raw_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (metric_id, piece_id, platform, like_count, repost_count, reply_count,
             json.dumps(raw_data) if raw_data else None),
        )
        self.conn.commit()
        return self.get(metric_id)

    def get(self, metric_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM piece_metrics WHERE id = ?", (metric_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_piece(self, piece_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM piece_metrics WHERE piece_id = ? ORDER BY fetched_at DESC",
            (piece_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row) -> dict:
        result = dict(row)
        if result.get("raw_data"):
            result["raw_data"] = json.loads(result["raw_data"])
        return result
