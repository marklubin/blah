"""Tests for PublishTools (agent tool for publishing rants)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blah.agents.tools.publish_tools import PublishTools
from blah.config.settings import BlahSettings
from blah.db.repository import PieceRepo, RantRepo


@pytest.fixture
def publish_tools(db: sqlite3.Connection, settings: BlahSettings) -> tuple:
    """Create a rant and return publish tools for it."""
    rant_repo = RantRepo(db)
    piece_repo = PieceRepo(db)

    # Create a rant with approved pieces
    rant = rant_repo.create(title="Test Rant")
    rant_repo.update(rant["id"], status="active")

    # Create an approved piece
    piece = piece_repo.create(rant["id"], "bluesky", "Test content for Bluesky")
    piece_repo.update(piece["id"], status="approved")

    tools = PublishTools(db, settings, rant["id"])
    return tools, rant["id"], piece["id"]


class TestPublishTools:
    def test_publish_rant_no_approved_pieces(self, db: sqlite3.Connection, settings: BlahSettings):
        """Publishing with no approved pieces returns error."""
        rant_repo = RantRepo(db)
        rant = rant_repo.create(title="Empty Rant")

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        assert result.is_error
        data = json.loads(result.content)
        assert "No approved pieces" in data["error"]

    def test_publish_rant_not_found(self, db: sqlite3.Connection, settings: BlahSettings):
        """Publishing nonexistent rant returns error."""
        tools = PublishTools(db, settings, "nonexistent123")
        result = tools.publish_rant()

        assert result.is_error
        data = json.loads(result.content)
        assert "not found" in data["error"]

    @patch("blah.adapters.bluesky.BlueskyAdapter")
    def test_publish_rant_success(
        self,
        mock_bsky_cls,
        db: sqlite3.Connection,
        tmp_blah_home: Path,
    ):
        """Successfully publishing a rant."""
        # Set up settings with Bluesky enabled
        settings = BlahSettings.load(blah_home=tmp_blah_home)
        settings.platforms["bluesky"] = MagicMock(
            enabled=True,
            handle="test.bsky.social",
            app_password="test-password",
        )

        # Create rant with approved piece
        rant_repo = RantRepo(db)
        piece_repo = PieceRepo(db)
        rant = rant_repo.create(title="Test Rant")
        rant_repo.update(rant["id"], status="active")
        piece = piece_repo.create(rant["id"], "bluesky", "Hello Bluesky!")
        piece_repo.update(piece["id"], status="approved")

        # Mock the adapter
        mock_adapter = MagicMock()
        mock_bsky_cls.return_value = mock_adapter
        mock_adapter.post.return_value = MagicMock(
            external_id="at://did:plc:abc/post/123",
            external_url="https://bsky.app/profile/test/post/123",
            platform="bluesky",
        )

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        assert not result.is_error
        data = json.loads(result.content)
        assert len(data["published"]) == 1
        assert data["published"][0]["platform"] == "bluesky"
        assert "bsky.app" in data["published"][0]["url"]

    def test_publish_rant_no_adapters(
        self,
        db: sqlite3.Connection,
        settings: BlahSettings,
    ):
        """Publishing with no configured adapters returns error."""
        # Settings has no enabled platforms by default
        rant_repo = RantRepo(db)
        piece_repo = PieceRepo(db)
        rant = rant_repo.create(title="Test")
        rant_repo.update(rant["id"], status="active")
        piece = piece_repo.create(rant["id"], "bluesky", "Content")
        piece_repo.update(piece["id"], status="approved")

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        assert result.is_error
        data = json.loads(result.content)
        assert "No platform adapters" in data["error"]

    @patch("blah.adapters.bluesky.BlueskyAdapter")
    def test_publish_rant_partial_failure(
        self,
        mock_bsky_cls,
        db: sqlite3.Connection,
        tmp_blah_home: Path,
    ):
        """Publishing reports both successes and failures."""
        settings = BlahSettings.load(blah_home=tmp_blah_home)
        settings.platforms["bluesky"] = MagicMock(
            enabled=True,
            handle="test.bsky.social",
            app_password="test-password",
        )

        rant_repo = RantRepo(db)
        piece_repo = PieceRepo(db)
        rant = rant_repo.create(title="Multi Piece Rant")
        rant_repo.update(rant["id"], status="active")

        # Create two pieces
        piece1 = piece_repo.create(rant["id"], "bluesky", "Piece 1")
        piece_repo.update(piece1["id"], status="approved")
        piece2 = piece_repo.create(rant["id"], "bluesky", "Piece 2")
        piece_repo.update(piece2["id"], status="approved")

        # Mock adapter to succeed on first, fail on second
        mock_adapter = MagicMock()
        mock_bsky_cls.return_value = mock_adapter
        mock_adapter.post.side_effect = [
            MagicMock(
                external_id="post1",
                external_url="https://bsky.app/post/1",
                platform="bluesky",
            ),
            RuntimeError("API rate limit"),
        ]

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        # Not marked as error since some succeeded
        data = json.loads(result.content)
        assert len(data["published"]) == 1
        assert len(data["failed"]) == 1
        assert "rate limit" in data["failed"][0]["error"]

    @patch("blah.adapters.bluesky.BlueskyAdapter")
    @patch("blah.adapters.twitter.TwitterAdapter")
    def test_publish_rant_multiple_platforms(
        self,
        mock_twitter_cls,
        mock_bsky_cls,
        db: sqlite3.Connection,
        tmp_blah_home: Path,
    ):
        """Publishing to multiple platforms."""
        settings = BlahSettings.load(blah_home=tmp_blah_home)
        settings.platforms["bluesky"] = MagicMock(
            enabled=True,
            handle="test.bsky.social",
            app_password="test-password",
        )
        settings.platforms["twitter"] = MagicMock(
            enabled=True,
            client_id="test_client_id",
            oauth2_token={
                "access_token": "tok",
                "refresh_token": "ref",
                "expires_at": 9999999999,
            },
            twitterapi_io_key=None,
        )

        rant_repo = RantRepo(db)
        piece_repo = PieceRepo(db)
        rant = rant_repo.create(title="Cross Platform Rant")
        rant_repo.update(rant["id"], status="active")

        # Create pieces for both platforms
        piece1 = piece_repo.create(rant["id"], "bluesky", "For Bluesky")
        piece_repo.update(piece1["id"], status="approved")
        piece2 = piece_repo.create(rant["id"], "twitter", "For Twitter")
        piece_repo.update(piece2["id"], status="approved")

        # Mock both adapters
        mock_bsky = MagicMock()
        mock_bsky_cls.return_value = mock_bsky
        mock_bsky.post.return_value = MagicMock(
            external_id="bsky123",
            external_url="https://bsky.app/post/123",
            platform="bluesky",
        )

        mock_twitter = MagicMock()
        mock_twitter_cls.return_value = mock_twitter
        mock_twitter.post.return_value = MagicMock(
            external_id="twitter456",
            external_url="https://x.com/user/status/456",
            platform="twitter",
        )

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        data = json.loads(result.content)
        assert len(data["published"]) == 2
        platforms = {p["platform"] for p in data["published"]}
        assert "bluesky" in platforms
        assert "twitter" in platforms

    def test_publish_rant_skipped_no_adapter(
        self,
        db: sqlite3.Connection,
        tmp_blah_home: Path,
    ):
        """Pieces for unconfigured platforms are skipped."""
        settings = BlahSettings.load(blah_home=tmp_blah_home)
        # No platforms configured

        rant_repo = RantRepo(db)
        piece_repo = PieceRepo(db)
        rant = rant_repo.create(title="Rant")
        rant_repo.update(rant["id"], status="active")
        piece = piece_repo.create(rant["id"], "mastodon", "For Mastodon")  # No adapter
        piece_repo.update(piece["id"], status="approved")

        tools = PublishTools(db, settings, rant["id"])
        result = tools.publish_rant()

        # Error because no adapters at all
        assert result.is_error
        data = json.loads(result.content)
        assert "No platform adapters" in data["error"]
