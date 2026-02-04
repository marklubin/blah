"""Tests for PublishService."""

from __future__ import annotations

import sqlite3

import pytest

from blah.db.repository import PieceRepo, RantRepo
from blah.services.publishing import PublishService
from tests.mocks.adapters import MockPlatformAdapter


@pytest.fixture
def rant_with_pieces(db: sqlite3.Connection):
    """Create a rant with approved pieces for testing."""
    rant_repo = RantRepo(db)
    piece_repo = PieceRepo(db)

    r = rant_repo.create(title="Test Rant", summary="Test summary")
    rant_repo.update(r["id"], status="active")

    p1 = piece_repo.create(r["id"], "bluesky", "Hello from Bluesky!")
    piece_repo.update(p1["id"], status="approved")

    p2 = piece_repo.create(r["id"], "twitter", "Hello from Twitter!")
    piece_repo.update(p2["id"], status="approved")

    return r["id"], [p1["id"], p2["id"]]


def test_publish_rant_success(db: sqlite3.Connection, rant_with_pieces):
    """Publishing approved pieces marks them as published."""
    rant_id, piece_ids = rant_with_pieces

    mock_bsky = MockPlatformAdapter("bluesky")
    mock_twitter = MockPlatformAdapter("twitter")
    adapters = {"bluesky": mock_bsky, "twitter": mock_twitter}

    service = PublishService(db, adapters)
    result = service.publish_rant(rant_id)

    assert len(result.published) == 2
    assert len(result.failed) == 0
    assert len(result.skipped) == 0

    # Check pieces are updated
    piece_repo = PieceRepo(db)
    for pid in piece_ids:
        piece = piece_repo.get(pid)
        assert piece["status"] == "published"
        assert piece["external_url"] is not None
        assert piece["published_at"] is not None

    # Check rant is marked complete
    rant = RantRepo(db).get(rant_id)
    assert rant["status"] == "complete"


def test_publish_rant_partial_failure(db: sqlite3.Connection, rant_with_pieces):
    """If one platform fails, the other still publishes."""
    rant_id, piece_ids = rant_with_pieces

    mock_bsky = MockPlatformAdapter("bluesky")
    mock_twitter = MockPlatformAdapter("twitter", fail_on_post=True)
    adapters = {"bluesky": mock_bsky, "twitter": mock_twitter}

    service = PublishService(db, adapters)
    result = service.publish_rant(rant_id)

    assert len(result.published) == 1
    assert len(result.failed) == 1

    piece_repo = PieceRepo(db)
    bsky_piece = piece_repo.get(piece_ids[0])
    assert bsky_piece["status"] == "published"

    twitter_piece = piece_repo.get(piece_ids[1])
    assert twitter_piece["status"] == "failed"
    assert twitter_piece["error"] is not None
    assert twitter_piece["retry_count"] == 1


def test_publish_rant_missing_adapter(db: sqlite3.Connection, rant_with_pieces):
    """Pieces for platforms without adapters are skipped."""
    rant_id, _ = rant_with_pieces

    # Only provide bluesky adapter, twitter pieces should be skipped
    mock_bsky = MockPlatformAdapter("bluesky")
    adapters = {"bluesky": mock_bsky}

    service = PublishService(db, adapters)
    result = service.publish_rant(rant_id)

    assert len(result.published) == 1
    assert len(result.skipped) == 1


def test_publish_rant_no_approved(db: sqlite3.Connection):
    """Publishing a rant with no approved pieces does nothing."""
    rant_repo = RantRepo(db)
    r = rant_repo.create(title="Empty Rant")

    service = PublishService(db, {})
    result = service.publish_rant(r["id"])

    assert result.total == 0
    assert result.summary == "nothing to publish"


def test_publish_rant_not_found(db: sqlite3.Connection):
    """Publishing a nonexistent rant raises ValueError."""
    service = PublishService(db, {})
    with pytest.raises(ValueError, match="not found"):
        service.publish_rant("nonexistent")


def test_publish_piece_retry(db: sqlite3.Connection, rant_with_pieces):
    """Retrying a failed piece works."""
    rant_id, piece_ids = rant_with_pieces
    piece_repo = PieceRepo(db)

    # First, fail the piece
    piece_repo.update(piece_ids[0], status="failed", error="first try failed", retry_count=1)

    mock_bsky = MockPlatformAdapter("bluesky")
    adapters = {"bluesky": mock_bsky}

    service = PublishService(db, adapters)
    result = service.publish_piece(piece_ids[0])

    assert len(result.published) == 1
    piece = piece_repo.get(piece_ids[0])
    assert piece["status"] == "published"


def test_publish_piece_wrong_status(db: sqlite3.Connection, rant_with_pieces):
    """Can't publish a draft piece."""
    rant_id, piece_ids = rant_with_pieces
    piece_repo = PieceRepo(db)
    piece_repo.update(piece_ids[0], status="draft")

    service = PublishService(db, {"bluesky": MockPlatformAdapter("bluesky")})
    with pytest.raises(ValueError, match="must be 'approved' or 'failed'"):
        service.publish_piece(piece_ids[0])


def test_publish_piece_not_found(db: sqlite3.Connection):
    """Retrying a nonexistent piece raises ValueError."""
    service = PublishService(db, {})
    with pytest.raises(ValueError, match="not found"):
        service.publish_piece("nonexistent")


def test_publish_records_adapter_calls(db: sqlite3.Connection, rant_with_pieces):
    """Mock adapter records the content that was posted."""
    rant_id, _ = rant_with_pieces

    mock_bsky = MockPlatformAdapter("bluesky")
    mock_twitter = MockPlatformAdapter("twitter")
    adapters = {"bluesky": mock_bsky, "twitter": mock_twitter}

    service = PublishService(db, adapters)
    service.publish_rant(rant_id)

    assert len(mock_bsky.posts) == 1
    assert mock_bsky.posts[0].text == "Hello from Bluesky!"

    assert len(mock_twitter.posts) == 1
    assert mock_twitter.posts[0].text == "Hello from Twitter!"


def test_publish_result_summary():
    """PublishResult.summary formats correctly."""
    from blah.services.publishing import PublishResult

    r = PublishResult(
        published=[{"id": "1"}],
        failed=[{"id": "2"}],
        skipped=[{"id": "3"}],
    )
    assert r.summary == "1 published, 1 failed, 1 skipped"
    assert r.total == 3
