"""Tests for database initialization and repository CRUD."""

from __future__ import annotations

import sqlite3

from blah.db.repository import ChatHistoryRepo, PieceRepo, RantRepo


def test_schema_creates_tables(db: sqlite3.Connection):
    """Verify all tables are created."""
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row["name"] for row in cursor.fetchall()}
    expected = {
        "rants",
        "pieces",
        "resources",
        "rant_resources",
        "piece_resources",
        "sources",
        "feed_items",
        "reports",
        "report_items",
        "chat_histories",
    }
    assert expected.issubset(tables)


def test_schema_creates_indexes(db: sqlite3.Connection):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = {row["name"] for row in cursor.fetchall()}
    assert "idx_feed_items_status" in indexes
    assert "idx_feed_items_author" in indexes
    assert "idx_feed_items_score" in indexes


def test_rant_crud(db: sqlite3.Connection):
    repo = RantRepo(db)

    # Create
    rant = repo.create(title="Test Rant", summary="A test")
    assert rant["title"] == "Test Rant"
    assert rant["summary"] == "A test"
    assert rant["status"] == "draft"
    assert rant["id"] is not None

    # Read
    fetched = repo.get(rant["id"])
    assert fetched["title"] == "Test Rant"

    # Update
    updated = repo.update(rant["id"], title="Updated Rant", status="active")
    assert updated["title"] == "Updated Rant"
    assert updated["status"] == "active"

    # List
    rants = repo.list_all()
    assert len(rants) == 1

    # Count
    assert repo.count() == 1

    # Delete
    assert repo.delete(rant["id"]) is True
    assert repo.get(rant["id"]) is None
    assert repo.count() == 0


def test_rant_delete_nonexistent(db: sqlite3.Connection):
    repo = RantRepo(db)
    assert repo.delete("nonexistent") is False


def test_piece_crud(db: sqlite3.Connection):
    rant_repo = RantRepo(db)
    piece_repo = PieceRepo(db)

    rant = rant_repo.create(title="Test Rant")

    # Create
    piece = piece_repo.create(
        rant_id=rant["id"],
        platform="bluesky",
        content="Hello Bluesky!",
        target={"langs": ["en"]},
    )
    assert piece["platform"] == "bluesky"
    assert piece["content"] == "Hello Bluesky!"
    assert piece["target"] == {"langs": ["en"]}
    assert piece["status"] == "draft"

    # Read
    fetched = piece_repo.get(piece["id"])
    assert fetched["content"] == "Hello Bluesky!"

    # Update
    updated = piece_repo.update(piece["id"], status="approved", content="Updated!")
    assert updated["status"] == "approved"
    assert updated["content"] == "Updated!"

    # List by rant
    pieces = piece_repo.list_by_rant(rant["id"])
    assert len(pieces) == 1

    # Count
    assert piece_repo.count() == 1


def test_piece_failed_list(db: sqlite3.Connection):
    rant_repo = RantRepo(db)
    piece_repo = PieceRepo(db)

    rant = rant_repo.create(title="Test")
    piece_repo.create(rant_id=rant["id"], platform="bluesky", content="ok")
    piece = piece_repo.create(rant_id=rant["id"], platform="twitter", content="fail")
    piece_repo.update(piece["id"], status="failed", error="Rate limited")

    failed = piece_repo.list_failed()
    assert len(failed) == 1
    assert failed[0]["error"] == "Rate limited"


def test_chat_history(db: sqlite3.Connection):
    repo = ChatHistoryRepo(db)

    # Empty initially
    assert repo.get("rant:1") == []

    # Save
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    repo.save("rant:1", messages)
    assert repo.get("rant:1") == messages

    # Update (upsert)
    messages.append({"role": "user", "content": "Create a rant"})
    repo.save("rant:1", messages)
    assert len(repo.get("rant:1")) == 3
