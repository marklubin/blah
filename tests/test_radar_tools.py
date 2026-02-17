"""Tests for Radar agent tools."""

from __future__ import annotations

import json
import sqlite3

import pytest

from blah.agents.tools.radar_tools import RadarConfigTools, RadarReportTools
from blah.db.repository import FeedItemRepo, ReportItemRepo, ReportRepo, SourceRepo
from tests.mocks.adapters import MockPlatformAdapter


class TestRadarConfigTools:
    """Tests for RadarConfigTools."""

    def test_add_source_account(self, db: sqlite3.Connection):
        """Can add an account source."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="bluesky",
            source_type="account",
            handle="karpathy.bsky.social",
        )

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert "source_id" in data

        # Verify in DB
        source_repo = SourceRepo(db)
        source = source_repo.get(data["source_id"])
        assert source["platform"] == "bluesky"
        assert source["type"] == "account"
        assert source["config"]["handle"] == "karpathy.bsky.social"

    def test_add_source_timeline(self, db: sqlite3.Connection):
        """Can add a timeline source."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="bluesky",
            source_type="timeline",
        )

        assert not result.is_error
        data = json.loads(result.content)
        assert "bluesky timeline" in data["message"]

    def test_add_source_search(self, db: sqlite3.Connection):
        """Can add a search source."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="bluesky",
            source_type="search",
            query="AI agents",
        )

        assert not result.is_error
        data = json.loads(result.content)
        assert 'search: "AI agents"' in data["message"]

    def test_add_source_account_requires_handle(self, db: sqlite3.Connection):
        """Account source requires handle."""
        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="bluesky",
            source_type="account",
        )

        assert result.is_error
        assert "handle" in result.content.lower()

    def test_add_source_search_requires_query(self, db: sqlite3.Connection):
        """Search source requires query."""
        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="bluesky",
            source_type="search",
        )

        assert result.is_error
        assert "query" in result.content.lower()

    def test_list_sources_empty(self, db: sqlite3.Connection):
        """List sources when none exist."""
        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.list_sources()

        assert "No sources" in result.content

    def test_list_sources_shows_all(self, db: sqlite3.Connection):
        """List sources shows all configured sources."""
        source_repo = SourceRepo(db)
        source_repo.create("bluesky", "timeline", {"label": "Timeline"})
        source_repo.create("bluesky", "account", {"handle": "test", "label": "@test"})

        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.list_sources()

        assert "Timeline" in result.content
        assert "@test" in result.content
        assert result.content.count("bluesky") >= 2

    def test_remove_source(self, db: sqlite3.Connection):
        """Can remove a source."""
        source_repo = SourceRepo(db)
        source = source_repo.create("bluesky", "timeline", {"label": "Timeline"})

        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.remove_source(source["id"])

        assert not result.is_error
        assert source_repo.get(source["id"]) is None

    def test_remove_source_not_found(self, db: sqlite3.Connection):
        """Removing nonexistent source fails."""
        adapters = {}
        tools = RadarConfigTools(db, adapters)

        result = tools.remove_source("nonexistent")

        assert result.is_error
        assert "not found" in result.content.lower()

    def test_toggle_source(self, db: sqlite3.Connection):
        """Can enable/disable a source."""
        source_repo = SourceRepo(db)
        source = source_repo.create("bluesky", "timeline", {"label": "Timeline"})

        adapters = {}
        tools = RadarConfigTools(db, adapters)

        # Disable
        result = tools.toggle_source(source["id"], False)
        assert not result.is_error
        assert "disabled" in result.content

        updated = source_repo.get(source["id"])
        assert not updated["enabled"]

        # Enable
        result = tools.toggle_source(source["id"], True)
        assert "enabled" in result.content


class TestRadarReportTools:
    """Tests for RadarReportTools."""

    @pytest.fixture
    def report_with_items(self, db: sqlite3.Connection):
        """Create a report with items for testing."""
        source_repo = SourceRepo(db)
        feed_repo = FeedItemRepo(db)
        report_repo = ReportRepo(db)
        report_item_repo = ReportItemRepo(db)

        # Create source and feed item
        source = source_repo.create("bluesky", "timeline", {"label": "Timeline"})
        feed_item = feed_repo.create(
            source_id=source["id"],
            platform="bluesky",
            external_id="at://did:plc:test/post/1",
            author="test.bsky.social",
            content="Test post about AI",
            url="https://bsky.app/profile/test/post/1",
        )

        # Create report
        report = report_repo.create(sources_polled=[source["id"]])

        # Create report item
        report_item = report_item_repo.create(
            report_id=report["id"],
            item_type="signal",
            data={
                "feed_item_id": feed_item["id"],
                "author": "test.bsky.social",
                "content": "Test post about AI",
                "url": "https://bsky.app/profile/test/post/1",
                "suggested_angles": ["Ask about their approach", "Share your experience"],
                "relevance_notes": "Discusses AI which is your interest",
            },
            relevance_score=0.85,
        )

        return report["id"], report_item["id"], feed_item["id"]

    def test_get_report_summary(self, db: sqlite3.Connection, report_with_items):
        """Can get report summary."""
        report_id, _, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.get_report_summary()

        assert not result.is_error
        assert report_id[:8] in result.content
        assert "pending" in result.content.lower()

    def test_list_report_items(self, db: sqlite3.Connection, report_with_items):
        """Can list report items."""
        report_id, _, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.list_report_items()

        assert not result.is_error
        assert "test.bsky.social" in result.content
        assert "0.85" in result.content  # Score

    def test_get_item_detail(self, db: sqlite3.Connection, report_with_items):
        """Can get item details with suggested angles."""
        report_id, item_id, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.get_item_detail(item_id[:8])

        assert not result.is_error
        assert "test.bsky.social" in result.content
        assert "Ask about their approach" in result.content
        assert "Share your experience" in result.content

    def test_mark_reviewed(self, db: sqlite3.Connection, report_with_items):
        """Can mark item as reviewed."""
        report_id, item_id, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.mark_reviewed(item_id[:8])

        assert not result.is_error
        assert "reviewed" in result.content.lower()

        # Verify in DB
        repo = ReportItemRepo(db)
        item = repo.get(item_id)
        assert item["status"] == "reviewed"

    def test_mark_skipped(self, db: sqlite3.Connection, report_with_items):
        """Can mark item as skipped."""
        report_id, item_id, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.mark_skipped(item_id[:8])

        assert not result.is_error

        repo = ReportItemRepo(db)
        item = repo.get(item_id)
        assert item["status"] == "skipped"

    def test_draft_reply(self, db: sqlite3.Connection, report_with_items):
        """Can draft a reply."""
        report_id, item_id, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.draft_reply(item_id[:8], "Great point! I've been thinking about this too.")

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert data["char_count"] < 300

    def test_draft_reply_too_long(self, db: sqlite3.Connection, report_with_items):
        """Draft fails if too long."""
        report_id, item_id, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        long_text = "x" * 400
        result = tools.draft_reply(item_id[:8], long_text)

        assert result.is_error
        assert "exceeds" in result.content.lower()

    def test_send_reply(self, db: sqlite3.Connection, report_with_items):
        """Can send a drafted reply."""
        report_id, item_id, feed_item_id = report_with_items

        mock_adapter = MockPlatformAdapter("bluesky")
        adapters = {"bluesky": mock_adapter}
        tools = RadarReportTools(db, adapters, report_id)

        # First draft
        tools.draft_reply(item_id[:8], "Test reply")

        # Then send
        result = tools.send_reply(item_id[:8])

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert "reply_url" in data

        # Verify adapter was called
        assert len(mock_adapter.posts) == 1
        assert mock_adapter.posts[0].text == "Test reply"

    def test_send_reply_no_draft(self, db: sqlite3.Connection, report_with_items):
        """Send fails without draft."""
        report_id, item_id, _ = report_with_items

        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.send_reply(item_id[:8])

        assert result.is_error
        assert "draft" in result.content.lower()

    def test_follow_author(self, db: sqlite3.Connection, report_with_items):
        """Can follow an author."""
        report_id, item_id, _ = report_with_items

        mock_adapter = MockPlatformAdapter("bluesky")
        adapters = {"bluesky": mock_adapter}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.follow_author(item_id[:8])

        assert not result.is_error
        assert "following" in result.content.lower()
        assert "test.bsky.social" in result.content

        # Verify adapter was called
        assert "test.bsky.social" in mock_adapter.followed

    def test_complete_report(self, db: sqlite3.Connection, report_with_items):
        """Can mark report as complete."""
        report_id, _, _ = report_with_items

        adapters = {}
        tools = RadarReportTools(db, adapters, report_id)

        result = tools.complete_report()

        assert not result.is_error
        assert "complete" in result.content.lower()

        # Verify in DB
        repo = ReportRepo(db)
        report = repo.get(report_id)
        assert report["status"] == "complete"

    def test_no_report_selected(self, db: sqlite3.Connection):
        """Tools fail when no report is selected."""
        adapters = {}
        tools = RadarReportTools(db, adapters, None)

        result = tools.list_report_items()
        assert result.is_error
        assert "no report" in result.content.lower()

        result = tools.get_report_summary()
        assert result.is_error
