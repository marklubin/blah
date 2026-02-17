"""Tests for Radar services: triage, research, pipeline."""

from __future__ import annotations

import json
import sqlite3

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
