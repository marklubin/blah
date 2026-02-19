"""Tests for LinkedIn tools."""

from __future__ import annotations

import json
import sqlite3

from blah.agents.tools.linkedin_tools import LinkedInTools
from blah.db.repository import FeedItemRepo, SourceRepo


class TestStoreLinkedInItems:
    """Tests for store_linkedin_items tool."""

    def test_store_linkedin_items(self, db: sqlite3.Connection):
        """Stores items and returns correct counts."""
        tools = LinkedInTools(db)

        items = [
            {"external_id": "post-1", "author": "Alice", "text": "Hello world", "url": "https://linkedin.com/post/1"},
            {"external_id": "post-2", "author": "Bob", "text": "Another post", "url": "https://linkedin.com/post/2"},
        ]

        result = tools.store_linkedin_items(json.dumps(items))

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert data["ingested"] == 2
        assert data["skipped"] == 0
        assert "source_id" in data

        # Verify items are in DB
        feed_repo = FeedItemRepo(db)
        item = feed_repo.get_by_external_id("linkedin", "post-1")
        assert item is not None
        assert item["author"] == "Alice"
        assert item["content"] == "Hello world"

    def test_store_linkedin_items_dedup(self, db: sqlite3.Connection):
        """Duplicate items are skipped."""
        tools = LinkedInTools(db)

        items = [
            {"external_id": "post-1", "author": "Alice", "text": "Hello world"},
        ]

        # First insert
        result1 = tools.store_linkedin_items(json.dumps(items))
        data1 = json.loads(result1.content)
        assert data1["ingested"] == 1

        # Second insert - should be skipped
        result2 = tools.store_linkedin_items(json.dumps(items))
        data2 = json.loads(result2.content)
        assert data2["ingested"] == 0
        assert data2["skipped"] == 1

    def test_store_linkedin_items_invalid_json(self, db: sqlite3.Connection):
        """Returns error for invalid JSON."""
        tools = LinkedInTools(db)

        result = tools.store_linkedin_items("not valid json{{{")

        assert result.is_error
        assert "Invalid JSON" in result.content

    def test_store_linkedin_items_not_array(self, db: sqlite3.Connection):
        """Returns error when input is not an array."""
        tools = LinkedInTools(db)

        result = tools.store_linkedin_items('{"key": "value"}')

        assert result.is_error
        assert "JSON array" in result.content


class TestCheckLinkedInAuth:
    """Tests for check_linkedin_auth tool."""

    def test_check_linkedin_auth(self, db: sqlite3.Connection):
        """Returns instructions with auth indicators."""
        tools = LinkedInTools(db)

        result = tools.check_linkedin_auth()

        assert not result.is_error
        data = json.loads(result.content)
        assert "instructions" in data
        assert "logged_in_indicators" in data
        assert "logged_out_indicators" in data
        assert "linkedin.com" in data["url"]


class TestGetScrapeInstructions:
    """Tests for get_scrape_instructions tool."""

    def test_get_scrape_instructions_feed(self, db: sqlite3.Connection):
        """Returns feed URL and instructions."""
        tools = LinkedInTools(db)

        result = tools.get_scrape_instructions(scrape_type="feed")

        assert not result.is_error
        data = json.loads(result.content)
        assert "linkedin.com/feed" in data["url"]
        assert len(data["instructions"]) > 0
        assert "extract_fields" in data

    def test_get_scrape_instructions_profile(self, db: sqlite3.Connection):
        """Returns profile URL with target handle."""
        tools = LinkedInTools(db)

        result = tools.get_scrape_instructions(scrape_type="profile", target="johndoe")

        assert not result.is_error
        data = json.loads(result.content)
        assert "johndoe" in data["url"]
        assert "recent-activity" in data["url"]

    def test_get_scrape_instructions_search(self, db: sqlite3.Connection):
        """Returns search URL with query."""
        tools = LinkedInTools(db)

        result = tools.get_scrape_instructions(scrape_type="search", target="AI agents")

        assert not result.is_error
        data = json.loads(result.content)
        assert "search/results/content" in data["url"]
        assert "AI" in data["url"]

    def test_get_scrape_instructions_profile_no_target(self, db: sqlite3.Connection):
        """Profile scrape without target returns error."""
        tools = LinkedInTools(db)

        result = tools.get_scrape_instructions(scrape_type="profile")

        assert result.is_error
        assert "target" in result.content.lower()


class TestGetLinkedInSources:
    """Tests for get_linkedin_sources tool."""

    def test_get_linkedin_sources_empty(self, db: sqlite3.Connection):
        """Returns message when no sources configured."""
        tools = LinkedInTools(db)

        result = tools.get_linkedin_sources()

        assert not result.is_error
        assert "No LinkedIn sources" in result.content

    def test_get_linkedin_sources_with_data(self, db: sqlite3.Connection):
        """Shows sources when they exist."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="linkedin",
            source_type="feed",
            config={"label": "My LinkedIn Feed"},
        )

        tools = LinkedInTools(db)

        result = tools.get_linkedin_sources()

        assert not result.is_error
        assert "LinkedIn sources:" in result.content
        assert "My LinkedIn Feed" in result.content
        assert "feed" in result.content
