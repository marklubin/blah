"""End-to-end tests for the HackerNews integration.

Exercises the full flow: source creation → pipeline poll → triage → research
→ report generation → report review via tools.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from blah.agents.tools.radar_tools import RadarConfigTools, RadarReportTools
from blah.db.repository import FeedItemRepo, ReportItemRepo, ReportRepo, SourceRepo
from blah.services.pipeline import RadarPipeline
from tests.mocks.adapters import MockPlatformAdapter
from tests.mocks.llm import MockLLMClient


# ── Helpers ──────────────────────────────────────────────────────


def _hn_item(id: int, title: str, score: int = 10, by: str = "pg") -> dict:
    """Build a pipeline-standard HN item dict for the mock adapter."""
    return {
        "uri": f"hn_{id}",
        "external_id": f"hn_{id}",
        "url": f"https://news.ycombinator.com/item?id={id}",
        "text": title,
        "author": {"handle": by, "display_name": by},
        "like_count": score,
        "reply_count": 0,
        "title": title,
    }


def _hn_adapter_with_frontpage(items: list[dict]) -> MockPlatformAdapter:
    """Create a mock HN adapter with frontpage items loaded."""
    adapter = MockPlatformAdapter("hackernews")
    adapter.frontpage_feeds["top"] = items
    adapter.search_results = items  # also available via search
    return adapter


# ── Source creation via RadarConfigTools ──────────────────────────


class TestHackerNewsSourceConfig:
    """Test creating HN sources through the config tools."""

    def test_add_frontpage_source(self, db: sqlite3.Connection):
        """Can add a frontpage source for HackerNews."""
        adapters = {"hackernews": MockPlatformAdapter("hackernews")}
        tools = RadarConfigTools(db, adapters)

        result = tools.add_source(
            platform="hackernews",
            source_type="frontpage",
            sort="top",
            label="HN front page",
        )

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True

        # Verify stored in DB with correct config
        source_repo = SourceRepo(db)
        source = source_repo.get(data["source_id"])
        assert source["platform"] == "hackernews"
        assert source["type"] == "frontpage"
        assert source["config"]["sort"] == "top"
        assert source["config"]["label"] == "HN front page"

    def test_add_frontpage_source_auto_label(self, db: sqlite3.Connection):
        """Frontpage source gets an auto-generated label when none provided."""
        tools = RadarConfigTools(db, {"hackernews": MockPlatformAdapter("hackernews")})

        result = tools.add_source(
            platform="hackernews",
            source_type="frontpage",
            sort="show",
        )

        assert not result.is_error
        data = json.loads(result.content)
        assert "show" in data["message"].lower()

    def test_add_account_source(self, db: sqlite3.Connection):
        """Can add a user account source for HackerNews."""
        tools = RadarConfigTools(db, {"hackernews": MockPlatformAdapter("hackernews")})

        result = tools.add_source(
            platform="hackernews",
            source_type="account",
            handle="dang",
        )

        assert not result.is_error
        data = json.loads(result.content)
        source = SourceRepo(db).get(data["source_id"])
        assert source["config"]["handle"] == "dang"

    def test_add_search_source(self, db: sqlite3.Connection):
        """Can add a search source for HackerNews."""
        tools = RadarConfigTools(db, {"hackernews": MockPlatformAdapter("hackernews")})

        result = tools.add_source(
            platform="hackernews",
            source_type="search",
            query="Show HN",
        )

        assert not result.is_error
        data = json.loads(result.content)
        source = SourceRepo(db).get(data["source_id"])
        assert source["config"]["query"] == "Show HN"

    def test_search_posts_hackernews(self, db: sqlite3.Connection):
        """search_posts tool works with HackerNews adapter."""
        adapter = MockPlatformAdapter("hackernews")
        adapter.search_results = [
            _hn_item(100, "Show HN: Cool Tool"),
            _hn_item(200, "Ask HN: What's new?"),
        ]
        tools = RadarConfigTools(db, {"hackernews": adapter})

        result = tools.search_posts(platform="hackernews", query="Show HN", limit=5)

        assert not result.is_error
        assert "Cool Tool" in result.content
        assert "What's new?" in result.content

    def test_get_profile_hackernews(self, db: sqlite3.Connection):
        """get_profile tool works with HackerNews adapter."""
        adapter = MockPlatformAdapter("hackernews")
        adapter.profiles["pg"] = {
            "handle": "pg",
            "display_name": "pg",
            "description": "Lisp hacker",
            "followers_count": 0,
            "posts_count": 5000,
        }
        tools = RadarConfigTools(db, {"hackernews": adapter})

        result = tools.get_profile(platform="hackernews", handle="pg")

        assert not result.is_error
        assert "pg" in result.content
        assert "Lisp hacker" in result.content

    def test_get_recent_posts_hackernews(self, db: sqlite3.Connection):
        """get_recent_posts tool works with HackerNews adapter."""
        adapter = MockPlatformAdapter("hackernews")
        adapter.author_feeds["dang"] = [
            _hn_item(300, "Flagged and moderated", by="dang"),
        ]
        tools = RadarConfigTools(db, {"hackernews": adapter})

        result = tools.get_recent_posts(platform="hackernews", handle="dang", limit=5)

        assert not result.is_error
        assert "moderated" in result.content


# ── Pipeline polling with frontpage source ───────────────────────


class TestFrontpageSourcePipeline:
    """Test the pipeline's handling of frontpage source type."""

    def test_frontpage_source_fetches(self, db: sqlite3.Connection, settings):
        """Frontpage source type calls get_frontpage on the adapter."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "top", "label": "HN front page"},
        )

        adapter = _hn_adapter_with_frontpage([
            _hn_item(100, "Show HN: New Thing", score=150, by="builder"),
            _hn_item(200, "AI just got smarter", score=300, by="researcher"),
        ])
        adapters = {"hackernews": adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert result["items_count"] == 2

        feed_repo = FeedItemRepo(db)
        items = feed_repo.list_by_status("raw")
        assert len(items) == 2
        assert all(i["platform"] == "hackernews" for i in items)

        ids = {i["external_id"] for i in items}
        assert "hn_100" in ids
        assert "hn_200" in ids

    def test_frontpage_deduplication(self, db: sqlite3.Connection, settings):
        """Same items polled twice are not duplicated."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "top", "label": "HN top"},
        )

        stories = [_hn_item(100, "Duplicate story")]
        adapter = _hn_adapter_with_frontpage(stories)
        adapters = {"hackernews": adapter}

        pipeline = RadarPipeline(db, settings, adapters)

        r1 = pipeline.poll_only()
        assert r1["items_count"] == 1

        r2 = pipeline.poll_only()
        assert r2["items_count"] == 0  # already stored

        feed_repo = FeedItemRepo(db)
        items = feed_repo.list_by_status("raw")
        assert len(items) == 1

    def test_frontpage_default_sort(self, db: sqlite3.Connection, settings):
        """Frontpage source defaults to 'top' when sort is not specified."""
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"label": "HN default"},  # no sort key
        )

        adapter = MockPlatformAdapter("hackernews")
        adapter.frontpage_feeds["top"] = [_hn_item(999, "Default sort story")]
        adapters = {"hackernews": adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert result["items_count"] == 1

    def test_multiple_hn_sources(self, db: sqlite3.Connection, settings):
        """Multiple HN sources (frontpage, account, search) all poll correctly."""
        source_repo = SourceRepo(db)

        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "new", "label": "HN new"},
        )
        source_repo.create(
            platform="hackernews",
            source_type="account",
            config={"handle": "pg", "label": "@pg"},
        )
        source_repo.create(
            platform="hackernews",
            source_type="search",
            config={"query": "LLM agents", "label": "LLM search"},
        )

        adapter = MockPlatformAdapter("hackernews")
        adapter.frontpage_feeds["new"] = [_hn_item(1, "New story")]
        adapter.author_feeds["pg"] = [_hn_item(2, "PG essay", by="pg")]
        adapter.search_results = [_hn_item(3, "LLM agents paper")]
        adapters = {"hackernews": adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert result["items_count"] == 3

        feed_repo = FeedItemRepo(db)
        items = feed_repo.list_by_status("raw")
        ids = {i["external_id"] for i in items}
        assert ids == {"hn_1", "hn_2", "hn_3"}


# ── Full pipeline: poll → triage → research → report ────────────


class TestHackerNewsFullPipeline:
    """End-to-end pipeline: HN frontpage → triage → research → report."""

    @patch("blah.services.pipeline.httpx.post")
    def test_full_flow(self, mock_notify, db: sqlite3.Connection, settings):
        """HN stories flow through the entire pipeline to a report."""
        mock_notify.return_value = MagicMock(status_code=200)

        # 1. Create a frontpage source
        source_repo = SourceRepo(db)
        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "top", "label": "HN front page"},
        )

        # 2. Set up mock adapter with stories
        adapter = _hn_adapter_with_frontpage([
            _hn_item(1001, "Show HN: Agent framework in Rust", score=200, by="rustdev"),
            _hn_item(1002, "LLMs can now reason about code", score=350, by="airesearcher"),
            _hn_item(1003, "Ask HN: Best CLI tools in 2026?", score=100, by="cliuser"),
        ])
        adapters = {"hackernews": adapter}

        # 3. Set up mock LLM for triage + research
        mock_llm = MockLLMClient()

        # Triage: all items score high
        triage_scores = [
            {"score": 0.9, "reason": "Agent framework — directly relevant"},
            {"score": 0.7, "reason": "LLM reasoning — interesting signal"},
            {"score": 0.6, "reason": "CLI tools — marginally relevant"},
        ]
        mock_llm.add_response(text=json.dumps(triage_scores))

        # Research: one response per item
        for title in [
            "Agent framework in Rust",
            "LLMs reason about code",
            "CLI tools discussion",
        ]:
            mock_llm.add_response(text=json.dumps({
                "relevance_notes": f"Discusses {title}",
                "angles": [
                    f"Share thoughts on {title}",
                    f"Ask about implementation details",
                ],
            }))

        # 4. Run the pipeline
        pipeline = RadarPipeline(db, settings, adapters)
        pipeline._triage._llm = mock_llm
        pipeline._research._llm = mock_llm

        result = pipeline.run()

        # 5. Verify results
        assert result.items_fetched == 3
        assert result.items_triaged == 3
        assert result.items_passed == 3
        assert result.items_researched == 3
        assert result.report_id is not None
        assert result.report_items == 3

        # Verify feed items stored correctly
        feed_repo = FeedItemRepo(db)
        reported_items = feed_repo.list_by_status("reported")
        assert len(reported_items) == 3
        assert all(i["platform"] == "hackernews" for i in reported_items)

        # Verify report exists
        report_repo = ReportRepo(db)
        report = report_repo.get(result.report_id)
        assert report["status"] == "pending"

        # Verify report items have enrichment
        report_item_repo = ReportItemRepo(db)
        report_items = report_item_repo.list_by_report(result.report_id)
        assert len(report_items) == 3
        for ri in report_items:
            data = ri["data"]
            assert len(data["suggested_angles"]) == 2
            assert data["relevance_notes"]

        # Verify notification was sent
        info_calls = [
            c for c in mock_notify.call_args_list
            if c.kwargs.get("json", c[1].get("json", {})).get("level") == "info"
        ]
        assert len(info_calls) >= 1

    @patch("blah.services.pipeline.httpx.post")
    def test_mixed_platforms(self, mock_notify, db: sqlite3.Connection, settings):
        """HN and other platform sources poll together without interference."""
        mock_notify.return_value = MagicMock(status_code=200)

        source_repo = SourceRepo(db)

        # HN frontpage
        source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "top", "label": "HN top"},
        )
        # Bluesky timeline
        source_repo.create(
            platform="bluesky",
            source_type="timeline",
            config={"label": "bsky timeline"},
        )

        hn_adapter = MockPlatformAdapter("hackernews")
        hn_adapter.frontpage_feeds["top"] = [_hn_item(500, "HN story")]

        bsky_adapter = MockPlatformAdapter("bluesky")
        bsky_adapter.timeline_items = [{
            "uri": "at://did:plc:test/post/1",
            "text": "Bluesky post",
            "author": {"handle": "test.bsky.social"},
        }]

        adapters = {"hackernews": hn_adapter, "bluesky": bsky_adapter}

        pipeline = RadarPipeline(db, settings, adapters)
        result = pipeline.poll_only()

        assert result["items_count"] == 2

        feed_repo = FeedItemRepo(db)
        items = feed_repo.list_by_status("raw")
        platforms = {i["platform"] for i in items}
        assert platforms == {"hackernews", "bluesky"}


# ── Report review via RadarReportTools ───────────────────────────


class TestHackerNewsReportReview:
    """Test reviewing HN report items through RadarReportTools."""

    @pytest.fixture
    def hn_report(self, db: sqlite3.Connection):
        """Create a complete HN report with items ready for review."""
        source_repo = SourceRepo(db)
        feed_repo = FeedItemRepo(db)
        report_repo = ReportRepo(db)
        report_item_repo = ReportItemRepo(db)

        # Source
        source = source_repo.create(
            platform="hackernews",
            source_type="frontpage",
            config={"sort": "top", "label": "HN top"},
        )

        # Feed items
        items = []
        for i, (title, author, score) in enumerate([
            ("Show HN: Build agents with Rust", "rustdev", 200),
            ("LLMs can reason about code now", "airesearcher", 350),
        ]):
            item = feed_repo.create(
                source_id=source["id"],
                platform="hackernews",
                external_id=f"hn_{1000 + i}",
                author=author,
                content=title,
                url=f"https://news.ycombinator.com/item?id={1000 + i}",
            )
            feed_repo.update(
                item["id"],
                status="reported",
                relevance_score=score / 400,
                enrichment={
                    "suggested_angles": [
                        f"Discuss {title} approach",
                        "Ask about benchmarks",
                    ],
                    "relevance_notes": f"Relevant: {title}",
                    "author_context": f"@{author} is active in this space",
                },
            )
            items.append(item)

        # Report
        report = report_repo.create(sources_polled=[source["id"]])
        for item in items:
            enrichment = feed_repo.get(item["id"]).get("enrichment", {})
            report_item_repo.create(
                report_id=report["id"],
                item_type="signal",
                data={
                    "feed_item_id": item["id"],
                    "url": f"https://news.ycombinator.com/item?id={item['external_id'][3:]}",
                    "author": item["author"],
                    "content": item["content"],
                    "suggested_angles": enrichment.get("suggested_angles", []),
                    "relevance_notes": enrichment.get("relevance_notes"),
                    "author_context": enrichment.get("author_context"),
                },
                relevance_score=feed_repo.get(item["id"]).get("relevance_score"),
            )

        report_items = report_item_repo.list_by_report(report["id"])
        return report["id"], [ri["id"] for ri in report_items], [i["id"] for i in items]

    def test_report_summary(self, db: sqlite3.Connection, hn_report):
        """Report summary shows correct counts for HN items."""
        report_id, _, _ = hn_report
        adapter = MockPlatformAdapter("hackernews")
        tools = RadarReportTools(db, {"hackernews": adapter}, report_id)

        result = tools.get_report_summary()

        assert not result.is_error
        assert "New: 2" in result.content

    def test_list_items(self, db: sqlite3.Connection, hn_report):
        """Report items list shows HN content with angles."""
        report_id, _, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        result = tools.list_report_items()

        assert not result.is_error
        assert "rustdev" in result.content
        assert "airesearcher" in result.content
        assert "Suggested angles" in result.content or "angles" in result.content.lower()

    def test_item_detail(self, db: sqlite3.Connection, hn_report):
        """Full item detail shows enrichment data."""
        report_id, report_item_ids, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        result = tools.get_item_detail(report_item_ids[0])

        assert not result.is_error
        # Should have author, angles, and relevance notes (order may vary)
        assert "benchmarks" in result.content.lower()
        assert "Relevant" in result.content
        assert "Suggested Engagement Angles" in result.content

    def test_mark_reviewed(self, db: sqlite3.Connection, hn_report):
        """Can mark HN report items as reviewed."""
        report_id, report_item_ids, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        result = tools.mark_reviewed(report_item_ids[0])
        assert not result.is_error

        # Verify in DB
        report_item_repo = ReportItemRepo(db)
        item = report_item_repo.list_by_report(report_id)
        statuses = {i["id"]: i["status"] for i in item}
        assert statuses[report_item_ids[0]] == "reviewed"
        assert statuses[report_item_ids[1]] == "new"

    def test_mark_skipped(self, db: sqlite3.Connection, hn_report):
        """Can mark HN report items as skipped."""
        report_id, report_item_ids, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        result = tools.mark_skipped(report_item_ids[1])

        assert not result.is_error
        report_item_repo = ReportItemRepo(db)
        items = report_item_repo.list_by_report(report_id)
        skipped = [i for i in items if i["status"] == "skipped"]
        assert len(skipped) == 1

    def test_draft_reply_respects_no_char_limit(self, db: sqlite3.Connection, hn_report):
        """HN has no write API, but drafting still works (char limit is generous)."""
        report_id, report_item_ids, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        reply_text = "Great project! Have you considered using WASM for portability?"
        result = tools.draft_reply(report_item_ids[0], reply_text)

        assert not result.is_error
        data = json.loads(result.content)
        assert data["success"] is True
        assert data["platform"] == "hackernews"
        assert data["reply_text"] == reply_text

    def test_complete_report(self, db: sqlite3.Connection, hn_report):
        """Can complete an HN report after review."""
        report_id, report_item_ids, _ = hn_report
        tools = RadarReportTools(db, {"hackernews": MockPlatformAdapter("hackernews")}, report_id)

        # Review items, then complete
        tools.mark_reviewed(report_item_ids[0])
        tools.mark_skipped(report_item_ids[1])

        result = tools.complete_report()
        assert not result.is_error

        report_repo = ReportRepo(db)
        report = report_repo.get(report_id)
        assert report["status"] == "complete"

    def test_follow_returns_false_for_hn(self, db: sqlite3.Connection, hn_report):
        """Following an HN author returns failure (no follow API)."""
        report_id, report_item_ids, _ = hn_report
        adapter = MockPlatformAdapter("hackernews")
        # Override follow to mimic the real adapter
        adapter.follow = lambda handle: False
        tools = RadarReportTools(db, {"hackernews": adapter}, report_id)

        result = tools.follow_author(report_item_ids[0])

        assert result.is_error
        assert "Failed to follow" in result.content
