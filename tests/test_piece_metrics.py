"""Tests for piece metrics tracking."""

from __future__ import annotations

import sqlite3

import pytest

from blah.db.repository import PieceMetricsRepo, PieceRepo, RantRepo
from blah.services.pipeline import RadarPipeline
from tests.mocks.adapters import MockPlatformAdapter


@pytest.fixture
def published_pieces(db: sqlite3.Connection):
    """Create published pieces with external_ids for testing."""
    rant_repo = RantRepo(db)
    piece_repo = PieceRepo(db)

    rant = rant_repo.create(title="Test rant", summary="Test summary")

    pieces = []
    for i in range(3):
        piece = piece_repo.create(
            rant_id=rant["id"],
            platform="bluesky",
            content=f"Test piece {i}",
        )
        piece_repo.update(
            piece["id"],
            status="published",
            external_id=f"at://did:plc:test/app.bsky.feed.post/piece{i}",
            external_url=f"https://bsky.app/profile/test/post/piece{i}",
        )
        pieces.append(piece_repo.get(piece["id"]))

    return pieces


class TestPieceMetricsRepo:
    """Tests for PieceMetricsRepo CRUD operations."""

    def test_create_and_get(self, db: sqlite3.Connection, published_pieces):
        """Create a metric snapshot and retrieve it."""
        repo = PieceMetricsRepo(db)
        piece = published_pieces[0]

        metric = repo.create(
            piece_id=piece["id"],
            platform="bluesky",
            like_count=42,
            repost_count=7,
            reply_count=3,
            raw_data={"uri": "test", "extra": "data"},
        )

        assert metric is not None
        assert metric["piece_id"] == piece["id"]
        assert metric["platform"] == "bluesky"
        assert metric["like_count"] == 42
        assert metric["repost_count"] == 7
        assert metric["reply_count"] == 3
        assert metric["raw_data"] == {"uri": "test", "extra": "data"}
        assert metric["fetched_at"] is not None

    def test_list_by_piece(self, db: sqlite3.Connection, published_pieces):
        """List metrics for a specific piece returns all snapshots."""
        repo = PieceMetricsRepo(db)
        piece = published_pieces[0]

        # Create multiple snapshots
        repo.create(piece_id=piece["id"], platform="bluesky", like_count=10)
        repo.create(piece_id=piece["id"], platform="bluesky", like_count=20)
        repo.create(piece_id=piece["id"], platform="bluesky", like_count=30)

        metrics = repo.list_by_piece(piece["id"])

        assert len(metrics) == 3
        like_counts = {m["like_count"] for m in metrics}
        assert like_counts == {10, 20, 30}

    def test_list_by_piece_empty(self, db: sqlite3.Connection):
        """Listing metrics for a nonexistent piece returns empty list."""
        repo = PieceMetricsRepo(db)
        assert repo.list_by_piece("nonexistent") == []

    def test_create_without_raw_data(self, db: sqlite3.Connection, published_pieces):
        """Create a metric snapshot without raw_data."""
        repo = PieceMetricsRepo(db)
        piece = published_pieces[0]

        metric = repo.create(
            piece_id=piece["id"],
            platform="bluesky",
            like_count=5,
        )

        assert metric["raw_data"] is None


class TestPieceRepoListPublished:
    """Tests for PieceRepo.list_published()."""

    def test_list_published_returns_only_published(
        self, db: sqlite3.Connection, published_pieces
    ):
        """list_published returns only pieces with status=published and external_id."""
        piece_repo = PieceRepo(db)
        rant_repo = RantRepo(db)

        # Create a draft piece (should not appear)
        rant = rant_repo.create(title="Draft rant")
        piece_repo.create(
            rant_id=rant["id"],
            platform="bluesky",
            content="Draft piece",
        )

        published = piece_repo.list_published()

        assert len(published) == 3
        for p in published:
            assert p["status"] == "published"
            assert p["external_id"] is not None

    def test_list_published_empty(self, db: sqlite3.Connection):
        """list_published returns empty list when no published pieces exist."""
        piece_repo = PieceRepo(db)
        assert piece_repo.list_published() == []


class TestTrackPublishedPieces:
    """Tests for RadarPipeline.track_published_pieces()."""

    def test_track_with_published_pieces(
        self, db: sqlite3.Connection, settings, published_pieces
    ):
        """track_published_pieces fetches metrics and stores snapshots."""
        mock_adapter = MockPlatformAdapter("bluesky")
        adapters = {"bluesky": mock_adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.track_published_pieces()

        assert result["tracked"] == 3
        assert result["failed"] == 0

        # Verify snapshots stored
        metrics_repo = PieceMetricsRepo(db)
        for piece in published_pieces:
            metrics = metrics_repo.list_by_piece(piece["id"])
            assert len(metrics) == 1
            assert metrics[0]["like_count"] == 10
            assert metrics[0]["repost_count"] == 3
            assert metrics[0]["reply_count"] == 5

    def test_track_no_published_pieces(self, db: sqlite3.Connection, settings):
        """track_published_pieces returns zeros when nothing to track."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.track_published_pieces()

        assert result["tracked"] == 0
        assert result["failed"] == 0

    def test_track_handles_adapter_failure(
        self, db: sqlite3.Connection, settings, published_pieces
    ):
        """track_published_pieces logs error and continues when get_post fails."""
        class FailingAdapter(MockPlatformAdapter):
            def __init__(self):
                super().__init__("bluesky")
                self._call_count = 0

            def get_post(self, external_id: str) -> dict | None:
                self._call_count += 1
                if self._call_count == 2:
                    raise ConnectionError("API unavailable")
                return super().get_post(external_id)

        adapters = {"bluesky": FailingAdapter()}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.track_published_pieces()

        # 2 tracked successfully, 1 failed
        assert result["tracked"] == 2
        assert result["failed"] == 1

    def test_track_skips_no_adapter(
        self, db: sqlite3.Connection, settings, published_pieces
    ):
        """track_published_pieces skips pieces when no adapter for their platform."""
        # Empty adapters dict — no adapter for bluesky
        adapters = {}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.track_published_pieces()

        assert result["tracked"] == 0
        assert result["failed"] == 0

    def test_track_handles_get_post_returns_none(
        self, db: sqlite3.Connection, settings, published_pieces
    ):
        """track_published_pieces counts as failed when get_post returns None."""
        class NoneAdapter(MockPlatformAdapter):
            def get_post(self, external_id: str) -> dict | None:
                return None

        adapters = {"bluesky": NoneAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.track_published_pieces()

        assert result["tracked"] == 0
        assert result["failed"] == 3
