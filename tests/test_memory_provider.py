"""Tests for the memory provider interface and file-based implementation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from blah.memory.file_provider import FileMemoryProvider
from blah.memory.provider import (
    EngagementPreferences,
    MemoryContext,
    MemoryProvider,
    TrackedPerson,
    UserInterests,
)


# --- MemoryContext.to_prompt_text() ---


class TestMemoryContextToPromptText:
    def test_empty_context(self):
        ctx = MemoryContext()
        assert ctx.to_prompt_text() == ""

    def test_raw_context_only(self):
        ctx = MemoryContext(raw_context="I am interested in AI.")
        assert ctx.to_prompt_text() == "I am interested in AI."

    def test_topics(self):
        ctx = MemoryContext(
            interests=UserInterests(topics=["AI agents", "distributed systems"])
        )
        text = ctx.to_prompt_text()
        assert "## Topics of Interest" in text
        assert "- AI agents" in text
        assert "- distributed systems" in text

    def test_keywords(self):
        ctx = MemoryContext(
            interests=UserInterests(keywords=["LLM", "RAG", "embeddings"])
        )
        text = ctx.to_prompt_text()
        assert "## Keywords to Watch" in text
        assert "LLM, RAG, embeddings" in text

    def test_negative_topics(self):
        ctx = MemoryContext(
            interests=UserInterests(negative_topics=["crypto scams"])
        )
        text = ctx.to_prompt_text()
        assert "## Topics to Avoid" in text
        assert "- crypto scams" in text

    def test_tracked_people(self):
        ctx = MemoryContext(
            tracked_people=[
                TrackedPerson(
                    name="Alice",
                    handles={"twitter": "alice123"},
                    reason="AI researcher",
                    priority="high",
                ),
                TrackedPerson(
                    name="Bob",
                    handles={"bluesky": "bob.bsky"},
                    reason="",
                    priority="normal",
                ),
            ]
        )
        text = ctx.to_prompt_text()
        assert "## Tracked People" in text
        assert "**Alice**" in text
        assert "twitter: @alice123" in text
        assert "AI researcher" in text
        assert "[high]" in text
        assert "**Bob**" in text
        # Normal priority should not show bracket tag
        assert "[normal]" not in text

    def test_engagement_voice(self):
        ctx = MemoryContext(
            engagement=EngagementPreferences(voice_notes="Be concise and technical.")
        )
        text = ctx.to_prompt_text()
        assert "## Voice & Style" in text
        assert "Be concise and technical." in text

    def test_engagement_style(self):
        ctx = MemoryContext(
            engagement=EngagementPreferences(style="Friendly but direct")
        )
        text = ctx.to_prompt_text()
        assert "## Engagement Style" in text
        assert "Friendly but direct" in text

    def test_engagement_avoid_topics(self):
        ctx = MemoryContext(
            engagement=EngagementPreferences(avoid_topics=["politics"])
        )
        text = ctx.to_prompt_text()
        assert "## Avoid These Topics" in text
        assert "- politics" in text

    def test_full_context(self):
        ctx = MemoryContext(
            interests=UserInterests(
                topics=["AI"],
                keywords=["LLM"],
                negative_topics=["spam"],
            ),
            tracked_people=[
                TrackedPerson(name="Alice", handles={"twitter": "alice"}, reason="researcher"),
            ],
            engagement=EngagementPreferences(
                voice_notes="Technical",
                style="Direct",
                avoid_topics=["politics"],
            ),
            raw_context="Background info here.",
        )
        text = ctx.to_prompt_text()
        assert text.startswith("Background info here.")
        assert "## Topics of Interest" in text
        assert "## Keywords to Watch" in text
        assert "## Topics to Avoid" in text
        assert "## Tracked People" in text
        assert "## Voice & Style" in text
        assert "## Engagement Style" in text
        assert "## Avoid These Topics" in text


# --- FileMemoryProvider ---


class TestFileMemoryProvider:
    def test_reads_context_md(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("My context content")

        provider = FileMemoryProvider(context_path=context_file)
        ctx = provider.get_context()
        assert ctx.raw_context == "My context content"

    def test_reads_memory_json(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("")
        memory_file = tmp_path / "memory.json"
        memory_file.write_text(json.dumps({
            "interests": {
                "topics": ["AI", "agents"],
                "keywords": ["LLM"],
                "negative_topics": ["spam"],
            },
            "tracked_people": [
                {
                    "name": "Alice",
                    "handles": {"twitter": "alice"},
                    "reason": "researcher",
                    "priority": "high",
                }
            ],
            "engagement": {
                "voice_notes": "Be brief",
                "avoid_topics": ["politics"],
                "style": "casual",
            },
        }))

        provider = FileMemoryProvider(
            context_path=context_file,
            memory_json_path=memory_file,
        )
        ctx = provider.get_context()

        assert ctx.interests.topics == ["AI", "agents"]
        assert ctx.interests.keywords == ["LLM"]
        assert ctx.interests.negative_topics == ["spam"]
        assert len(ctx.tracked_people) == 1
        assert ctx.tracked_people[0].name == "Alice"
        assert ctx.tracked_people[0].handles == {"twitter": "alice"}
        assert ctx.tracked_people[0].priority == "high"
        assert ctx.engagement.voice_notes == "Be brief"
        assert ctx.engagement.avoid_topics == ["politics"]
        assert ctx.engagement.style == "casual"

    def test_missing_context_md(self, tmp_path: Path):
        provider = FileMemoryProvider(context_path=tmp_path / "nonexistent.md")
        ctx = provider.get_context()
        assert ctx.raw_context == ""

    def test_missing_memory_json(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("hello")

        provider = FileMemoryProvider(
            context_path=context_file,
            memory_json_path=tmp_path / "nonexistent.json",
        )
        ctx = provider.get_context()
        assert ctx.raw_context == "hello"
        assert ctx.interests.topics == []
        assert ctx.tracked_people == []

    def test_invalid_memory_json(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("hello")
        memory_file = tmp_path / "memory.json"
        memory_file.write_text("not valid json {{{")

        provider = FileMemoryProvider(
            context_path=context_file,
            memory_json_path=memory_file,
        )
        ctx = provider.get_context()
        # Should fall back gracefully
        assert ctx.raw_context == "hello"
        assert ctx.interests.topics == []
        assert ctx.tracked_people == []

    def test_no_memory_json_path(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("content")

        provider = FileMemoryProvider(context_path=context_file, memory_json_path=None)
        ctx = provider.get_context()
        assert ctx.raw_context == "content"
        assert ctx.interests.topics == []

    def test_caching(self, tmp_path: Path):
        context_file = tmp_path / "context.md"
        context_file.write_text("first")

        provider = FileMemoryProvider(context_path=context_file)
        ctx1 = provider.get_context()
        assert ctx1.raw_context == "first"

        # Modify file — cached result should still be "first"
        context_file.write_text("second")
        ctx2 = provider.get_context()
        assert ctx2.raw_context == "first"

        # After refresh, should pick up new content
        provider.refresh()
        ctx3 = provider.get_context()
        assert ctx3.raw_context == "second"

    def test_partial_memory_json(self, tmp_path: Path):
        """memory.json with only some fields should still work."""
        context_file = tmp_path / "context.md"
        context_file.write_text("")
        memory_file = tmp_path / "memory.json"
        memory_file.write_text(json.dumps({
            "interests": {"topics": ["AI"]},
        }))

        provider = FileMemoryProvider(
            context_path=context_file,
            memory_json_path=memory_file,
        )
        ctx = provider.get_context()
        assert ctx.interests.topics == ["AI"]
        assert ctx.interests.keywords == []
        assert ctx.tracked_people == []
        assert ctx.engagement.voice_notes == ""


# --- Protocol compliance ---


class TestProtocolCompliance:
    def test_file_provider_is_memory_provider(self, tmp_path: Path):
        provider = FileMemoryProvider(context_path=tmp_path / "ctx.md")
        assert isinstance(provider, MemoryProvider)
