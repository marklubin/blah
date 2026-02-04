"""Publishing service — posts approved pieces to platforms."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from blah.adapters.base import PlatformAdapter, PostContent
from blah.db.repository import PieceRepo, RantRepo

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of a publish operation across pieces."""

    published: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.published) + len(self.failed) + len(self.skipped)

    @property
    def summary(self) -> str:
        parts = []
        if self.published:
            parts.append(f"{len(self.published)} published")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts) if parts else "nothing to publish"


class PublishService:
    """Publishes approved pieces for a rant using platform adapters."""

    def __init__(
        self,
        db: sqlite3.Connection,
        adapters: dict[str, PlatformAdapter],
    ):
        self._rant_repo = RantRepo(db)
        self._piece_repo = PieceRepo(db)
        self._adapters = adapters

    def publish_rant(self, rant_id: str) -> PublishResult:
        """Publish all approved pieces for a rant."""
        rant = self._rant_repo.get(rant_id)
        if rant is None:
            raise ValueError(f"Rant {rant_id} not found")

        pieces = self._piece_repo.list_by_rant(rant_id)
        approved = [p for p in pieces if p["status"] == "approved"]

        if not approved:
            logger.info("No approved pieces for rant %s", rant_id)
            return PublishResult()

        result = PublishResult()

        for piece in approved:
            platform = piece["platform"]
            adapter = self._adapters.get(platform)

            if adapter is None:
                logger.warning(
                    "No adapter for platform '%s', skipping piece %s", platform, piece["id"],
                )
                result.skipped.append(piece)
                continue

            self._publish_piece(piece, adapter, result)

        # If all approved pieces are now published, mark rant as complete
        all_pieces = self._piece_repo.list_by_rant(rant_id)
        all_published = all(
            p["status"] in ("published", "failed") for p in all_pieces if p["status"] != "draft"
        )
        if all_published and result.published:
            self._rant_repo.update(rant_id, status="complete")

        return result

    def publish_piece(self, piece_id: str) -> PublishResult:
        """Publish a single piece (for retry)."""
        piece = self._piece_repo.get(piece_id)
        if piece is None:
            raise ValueError(f"Piece {piece_id} not found")

        if piece["status"] not in ("approved", "failed"):
            raise ValueError(
                f"Piece {piece_id} is '{piece['status']}', "
                "must be 'approved' or 'failed' to publish"
            )

        adapter = self._adapters.get(piece["platform"])
        if adapter is None:
            raise ValueError(f"No adapter configured for platform '{piece['platform']}'")

        result = PublishResult()
        self._publish_piece(piece, adapter, result)
        return result

    def _publish_piece(
        self,
        piece: dict,
        adapter: PlatformAdapter,
        result: PublishResult,
    ) -> None:
        """Attempt to publish a single piece."""
        piece_id = piece["id"]

        # Mark as publishing
        self._piece_repo.update(piece_id, status="publishing")

        try:
            content = PostContent(text=piece["content"])
            post_result = adapter.post(content)

            self._piece_repo.update(
                piece_id,
                status="published",
                external_id=post_result.external_id,
                external_url=post_result.external_url,
                published_at=datetime.now().isoformat(),
                error=None,
            )

            updated = self._piece_repo.get(piece_id)
            result.published.append(updated)
            logger.info(
                "Published piece %s to %s: %s",
                piece_id, piece["platform"], post_result.external_url,
            )

        except Exception as e:
            retry_count = piece.get("retry_count", 0) or 0
            self._piece_repo.update(
                piece_id,
                status="failed",
                error=str(e),
                retry_count=retry_count + 1,
            )

            updated = self._piece_repo.get(piece_id)
            result.failed.append(updated)
            logger.exception("Failed to publish piece %s to %s", piece_id, piece["platform"])
