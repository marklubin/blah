"""Tests for Radar services: triage, research, pipeline."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from blah.db.repository import FeedItemRepo, ReportItemRepo, ReportRepo, SourceRepo
from blah.services.pipeline import PipelineResult, RadarPipeline
from blah.services.research import Enrichment, ResearchService
from blah.services.triage import TriageResult, TriageService
from tests.mocks.adapters import MockPlatformAdapter
from tests.mocks.llm import MockLLMClient


@pytest.fixture
def source_with_items(db: sqlite3.Connection):
    """Create a source with raw feed items for testing."""
    source_repo = SourceRepo(db)
    feed_repo = FeedItemRepo(db)

    # Create source (label stored in config)
    source = source_repo.create(
        platform="bluesky",
        source_type="account",
        config={"handle": "test.bsky.social", "label": "@test"},
    )

    # Create raw feed items
    items = []
    for i in range(5):
        item = feed_repo.create(
            source_id=source["id"],
            platform="bluesky",
            external_id=f"at://did:plc:test/app.bsky.feed.post/{i}",
            author=f"author{i}.bsky.social",
            content=f"Test post {i} about AI and memory systems",
            url=f"https://bsky.app/profile/author{i}/post/{i}",
        )
        items.append(item)

    return source["id"], [item["id"] for item in items]


class TestTriageService:
    """Tests for TriageService."""

    def test_triage_empty(self, db: sqlite3.Connection, settings):
        """Triaging with no raw items returns empty result."""
        mock_llm = MockLLMClient()
        service = TriageService(db, settings, mock_llm)

        result = service.triage_raw_items()

        assert isinstance(result, TriageResult)
        assert result.total == 0
        assert len(result.passed) == 0
        assert len(result.discarded) == 0

    def test_triage_scores_items(self, db: sqlite3.Connection, settings, source_with_items):
        """Triage service scores items and updates their status."""
        source_id, item_ids = source_with_items

        # Mock LLM returns scores above and below threshold
        scores = [
            {"score": 0.8, "reason": "Highly relevant to AI"},
            {"score": 0.5, "reason": "Somewhat relevant"},
            {"score": 0.1, "reason": "Off-topic"},
            {"score": 0.9, "reason": "Very relevant"},
            {"score": 0.2, "reason": "Not interesting"},
        ]
        mock_llm = MockLLMClient()
        mock_llm.add_response(text=json.dumps(scores))
        service = TriageService(db, settings, mock_llm)

        result = service.triage_raw_items()

        assert result.total == 5
        assert len(result.passed) == 3  # 0.8, 0.5, 0.9 >= 0.3
        assert len(result.discarded) == 2  # 0.1, 0.2 < 0.3

        # Check items were updated in DB
        feed_repo = FeedItemRepo(db)
        for pid in item_ids[:3]:  # First three should pass (assuming order)
            item = feed_repo.get(item_ids[0])
            # Status should be either triaged or discarded
            assert item["status"] in ("triaged", "discarded")

    def test_triage_handles_llm_error(self, db: sqlite3.Connection, settings, source_with_items):
        """Triage handles LLM errors gracefully."""
        source_id, item_ids = source_with_items

        mock_llm = MockLLMClient()
        mock_llm.add_response(text="invalid json")
        service = TriageService(db, settings, mock_llm)

        result = service.triage_raw_items()

        # All items should be discarded with 0.0 scores on error
        assert result.total == 5
        assert len(result.discarded) == 5


class TestResearchService:
    """Tests for ResearchService."""

    def test_research_empty(self, db: sqlite3.Connection, settings):
        """Researching with no triaged items returns empty result."""
        mock_llm = MockLLMClient()
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        service = ResearchService(db, settings, adapters, mock_llm)

        result = service.research_triaged_items()

        assert result.total == 0
        assert len(result.researched) == 0

    def test_research_enriches_items(self, db: sqlite3.Connection, settings, source_with_items):
        """Research service enriches items with angles and context."""
        source_id, item_ids = source_with_items
        feed_repo = FeedItemRepo(db)

        # Mark items as triaged
        for item_id in item_ids[:2]:
            feed_repo.update(item_id, status="triaged")

        # Mock LLM returns engagement angles
        angles_response = json.dumps({
            "relevance_notes": "This discusses AI memory systems",
            "angles": [
                "Share your experience with similar systems",
                "Ask about their implementation approach",
            ],
        })
        mock_llm = MockLLMClient()
        mock_llm.add_response(text=angles_response)
        mock_llm.add_response(text=angles_response)
        mock_adapter = MockPlatformAdapter("bluesky")
        adapters = {"bluesky": mock_adapter}

        service = ResearchService(db, settings, adapters, mock_llm)
        result = service.research_triaged_items()

        assert result.total == 2
        assert len(result.researched) == 2

        # Check enrichment was stored
        for item in result.researched:
            assert "enrichment" in item
            assert "suggested_angles" in item["enrichment"]

    def test_enrichment_dataclass(self):
        """Enrichment dataclass converts to dict correctly."""
        enrichment = Enrichment(
            full_thread="Thread content",
            author_context="@user is a developer",
            related_posts=["post1", "post2"],
            suggested_angles=["Angle 1", "Angle 2"],
            relevance_notes="Very relevant",
        )

        d = enrichment.to_dict()

        assert d["full_thread"] == "Thread content"
        assert d["author_context"] == "@user is a developer"
        assert len(d["related_posts"]) == 2
        assert len(d["suggested_angles"]) == 2


class TestRadarPipeline:
    """Tests for RadarPipeline."""

    def test_pipeline_no_sources(self, db: sqlite3.Connection, settings):
        """Pipeline with no sources does nothing."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.run()

        assert result.items_fetched == 0
        assert result.items_triaged == 0
        assert result.report_id is None

    def test_pipeline_result_summary(self):
        """PipelineResult.summary formats correctly."""
        result = PipelineResult(
            sources_polled=["s1", "s2"],
            items_fetched=10,
            items_triaged=8,
            items_passed=5,
            items_discarded=3,
            items_researched=5,
            report_id="abc123",
            report_items=5,
        )

        summary = result.summary
        assert "10" in summary  # items fetched
        assert "2 sources" in summary
        assert "5 passed" in summary
        assert "5 items" in summary  # researched or report

    def test_pipeline_skip_poll(self, db: sqlite3.Connection, settings, source_with_items):
        """Pipeline with skip_poll uses existing raw items."""
        source_id, item_ids = source_with_items

        # Mock LLM for triage (high scores so items pass)
        scores = [{"score": 0.8, "reason": "Relevant"}] * 5
        angles = {"relevance_notes": "Test", "angles": ["Angle 1"]}

        # Need enough responses for triage + research calls
        mock_llm = MockLLMClient()
        mock_llm.add_response(text=json.dumps(scores))
        for _ in range(5):
            mock_llm.add_response(text=json.dumps(angles))

        # Patch the LLM client in the services
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)
        pipeline._triage._llm = mock_llm
        pipeline._research._llm = mock_llm

        result = pipeline.run(skip_poll=True)

        assert result.items_fetched == 0  # Didn't poll
        assert result.items_triaged == 5  # Used existing items

    def test_poll_only(self, db: sqlite3.Connection, settings):
        """poll_only just fetches without triage/research."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="bluesky",
            source_type="timeline",
            config={"label": "timeline"},
        )

        mock_adapter = MockPlatformAdapter("bluesky")
        mock_adapter.timeline_items = [
            {"uri": "at://test/1", "text": "Hello", "author": {"handle": "test"}}
        ]
        adapters = {"bluesky": mock_adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert "sources" in result
        assert "items_count" in result


class TestReportGeneration:
    """Tests for report generation in pipeline."""

    def test_report_created_with_researched_items(
        self, db: sqlite3.Connection, settings, source_with_items
    ):
        """Report is created from researched items."""
        source_id, item_ids = source_with_items
        feed_repo = FeedItemRepo(db)
        report_repo = ReportRepo(db)

        # Mark items as researched with enrichment
        for item_id in item_ids[:3]:
            feed_repo.update(
                item_id,
                status="researched",
                enrichment={
                    "suggested_angles": ["Test angle"],
                    "relevance_notes": "Test notes",
                },
            )

        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        # Call internal method directly
        result = pipeline._generate_report(["source1"])

        assert result["id"] is not None
        assert result["item_count"] == 3

        # Verify report in DB
        report = report_repo.get(result["id"])
        assert report is not None
        assert report["status"] == "pending"

        # Verify report items
        report_item_repo = ReportItemRepo(db)
        items = report_item_repo.list_by_report(result["id"])
        assert len(items) == 3

    def test_report_items_have_enrichment_data(
        self, db: sqlite3.Connection, settings, source_with_items
    ):
        """Report items contain the enrichment data from research."""
        source_id, item_ids = source_with_items
        feed_repo = FeedItemRepo(db)

        # Mark item as researched
        feed_repo.update(
            item_ids[0],
            status="researched",
            enrichment={
                "suggested_angles": ["Ask about their approach", "Share your experience"],
                "relevance_notes": "Discusses AI memory which is your interest",
                "author_context": "@author0 is an AI researcher",
            },
            relevance_score=0.85,
        )

        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline._generate_report([])

        report_item_repo = ReportItemRepo(db)
        items = report_item_repo.list_by_report(result["id"])

        assert len(items) == 1
        data = items[0]["data"]
        assert len(data["suggested_angles"]) == 2
        assert "AI memory" in data["relevance_notes"]


class TestSubredditSource:
    """Tests for subreddit source type in pipeline."""

    def test_subreddit_source_fetches(self, db: sqlite3.Connection, settings):
        """Subreddit source type calls get_subreddit_feed on the adapter."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="reddit",
            source_type="subreddit",
            config={"subreddit": "python", "label": "r/python"},
        )

        mock_adapter = MockPlatformAdapter("reddit")
        mock_adapter.subreddit_feeds["python"] = [
            {
                "uri": "t3_abc123",
                "external_id": "t3_abc123",
                "text": "Python post",
                "author": {"handle": "pydev"},
                "url": "https://reddit.com/r/python/abc123",
            }
        ]
        adapters = {"reddit": mock_adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert result["items_count"] == 1

        # Verify feed item stored
        feed_repo = FeedItemRepo(db)
        items = feed_repo.list_by_status("raw")
        assert len(items) == 1
        assert items[0]["platform"] == "reddit"
        assert items[0]["external_id"] == "t3_abc123"


class TestLinkedInSkip:
    """Tests for LinkedIn source handling in pipeline."""

    def test_linkedin_sources_skipped_during_poll(self, db: sqlite3.Connection, settings):
        """LinkedIn sources are skipped during polling (no adapter)."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="linkedin",
            source_type="feed",
            config={"label": "LinkedIn feed"},
        )

        adapters = {}
        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        # LinkedIn source should be skipped, not cause an error
        assert result["sources"] == []
        assert result["items_count"] == 0

    def test_linkedin_items_processed_with_skip_poll(self, db: sqlite3.Connection, settings):
        """Pre-ingested LinkedIn items are processed when skip_poll is used."""
        source_repo = SourceRepo(db)
        feed_repo = FeedItemRepo(db)

        # Create LinkedIn source and manually add a raw item (simulating ingest)
        source = source_repo.create(
            platform="linkedin",
            source_type="feed",
            config={"label": "LinkedIn feed"},
        )
        feed_repo.create(
            source_id=source["id"],
            platform="linkedin",
            external_id="urn:li:activity:123",
            author="Jane Doe",
            content="Interesting post about AI",
            url="https://linkedin.com/feed/update/urn:li:activity:123",
        )

        # Verify raw items exist
        raw_items = feed_repo.list_by_status("raw")
        assert len(raw_items) == 1
        assert raw_items[0]["platform"] == "linkedin"


class TestPipelineNotifications:
    """Tests for pipeline notification integration."""

    def test_notify_url_default_port(self, db: sqlite3.Connection, settings):
        """Pipeline defaults to port 8080 for notifications."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)
        assert "8080" in pipeline._notify_url

    def test_notify_url_custom_port(self, db: sqlite3.Connection, settings, monkeypatch):
        """Pipeline reads ROUTER_PORT from environment."""
        monkeypatch.setenv("ROUTER_PORT", "9999")
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)
        assert "9999" in pipeline._notify_url

    @patch("blah.services.pipeline.httpx.post")
    def test_notify_sends_post(self, mock_post, db: sqlite3.Connection, settings):
        """_notify sends an HTTP POST with correct payload."""
        mock_post.return_value = MagicMock(status_code=200)
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        pipeline._notify("info", "Test notification", metadata={"key": "val"})

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert payload["level"] == "info"
        assert payload["source"] == "blah-radar"
        assert payload["title"] == "Test notification"
        assert payload["metadata"]["key"] == "val"

    @patch("blah.services.pipeline.httpx.post")
    def test_notify_logs_failure_without_raising(self, mock_post, db: sqlite3.Connection, settings, caplog):
        """_notify logs the failure but doesn't raise, so the pipeline continues."""
        mock_post.side_effect = Exception("Connection refused")
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        # Should not raise
        pipeline._notify("error", "Something broke")

        # But it should have logged a warning
        assert any("Failed to push notification" in r.message for r in caplog.records)

    @patch("blah.services.pipeline.httpx.post")
    def test_pipeline_notifies_on_report(
        self, mock_post, db: sqlite3.Connection, settings, source_with_items
    ):
        """Pipeline sends info notification after generating a report."""
        mock_post.return_value = MagicMock(status_code=200)
        source_id, item_ids = source_with_items

        # Set up items so they pass triage and research
        scores = [{"score": 0.8, "reason": "Relevant"}] * 5
        angles = {"relevance_notes": "Test", "angles": ["Angle 1"]}
        mock_llm = MockLLMClient()
        mock_llm.add_response(text=json.dumps(scores))
        for _ in range(5):
            mock_llm.add_response(text=json.dumps(angles))

        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)
        pipeline._triage._llm = mock_llm
        pipeline._research._llm = mock_llm

        result = pipeline.run(skip_poll=True)

        # Should have a report
        assert result.report_id is not None

        # Should have called _notify (httpx.post) with report info
        assert mock_post.called
        # Find the info notification call
        info_calls = [
            c for c in mock_post.call_args_list
            if c.kwargs.get("json", c[1].get("json", {})).get("level") == "info"
        ]
        assert len(info_calls) >= 1
        payload = info_calls[0].kwargs.get("json") or info_calls[0][1]["json"]
        assert "Report ready" in payload["title"]
        assert payload["metadata"]["report_id"] == result.report_id

    @patch("blah.services.pipeline.httpx.post")
    def test_pipeline_notifies_on_poll_failure(
        self, mock_post, db: sqlite3.Connection, settings
    ):
        """Pipeline sends warning notification when a source fails to poll."""
        mock_post.return_value = MagicMock(status_code=200)

        # Create a source
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="bluesky",
            source_type="account",
            config={"handle": "fail.bsky.social", "label": "@fail"},
        )

        # Adapter that throws
        failing_adapter = MockPlatformAdapter("bluesky")
        failing_adapter.should_fail = True
        adapters = {"bluesky": failing_adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        pipeline.run()

        # Should have sent a warning notification
        warning_calls = [
            c for c in mock_post.call_args_list
            if c.kwargs.get("json", c[1].get("json", {})).get("level") == "warning"
        ]
        assert len(warning_calls) >= 1
        payload = warning_calls[0].kwargs.get("json") or warning_calls[0][1]["json"]
        assert "Failed to poll" in payload["title"]

    @patch("blah.services.pipeline.httpx.post")
    def test_pipeline_no_notification_when_no_report(
        self, mock_post, db: sqlite3.Connection, settings
    ):
        """Pipeline doesn't send info notification if no report is generated."""
        adapters = {"bluesky": MockPlatformAdapter("bluesky")}
        pipeline = RadarPipeline(db, settings, adapters)

        result = pipeline.run()

        assert result.report_id is None
        # Should not have called _notify for report (no info-level calls)
        info_calls = [
            c for c in mock_post.call_args_list
            if c.kwargs.get("json", c[1].get("json", {})).get("level") == "info"
        ]
        assert len(info_calls) == 0
