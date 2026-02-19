"""File-based memory provider — reads context.md + optional memory.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from blah.memory.provider import (
    EngagementPreferences,
    MemoryContext,
    TrackedPerson,
    UserInterests,
)

logger = logging.getLogger(__name__)


class FileMemoryProvider:
    """Reads context.md (always) and optional memory.json for structured data."""

    def __init__(self, context_path: Path, memory_json_path: Path | None = None):
        self._context_path = context_path
        self._memory_json_path = memory_json_path
        self._cached: MemoryContext | None = None

    def get_context(self) -> MemoryContext:
        if self._cached is None:
            self.refresh()
        return self._cached  # type: ignore[return-value]

    def refresh(self) -> None:
        raw_context = self._read_context_md()
        interests, people, engagement = self._read_memory_json()

        self._cached = MemoryContext(
            interests=interests,
            tracked_people=people,
            engagement=engagement,
            raw_context=raw_context,
        )

    def _read_context_md(self) -> str:
        try:
            return self._context_path.read_text()
        except FileNotFoundError:
            logger.info("No context.md found at %s", self._context_path)
            return ""
        except Exception:
            logger.exception("Failed to read context.md at %s", self._context_path)
            return ""

    def _read_memory_json(self) -> tuple[UserInterests, list[TrackedPerson], EngagementPreferences]:
        if not self._memory_json_path:
            return UserInterests(), [], EngagementPreferences()

        try:
            data = json.loads(self._memory_json_path.read_text())
        except FileNotFoundError:
            logger.debug("No memory.json found at %s (optional)", self._memory_json_path)
            return UserInterests(), [], EngagementPreferences()
        except json.JSONDecodeError:
            logger.exception("Invalid JSON in memory.json at %s", self._memory_json_path)
            return UserInterests(), [], EngagementPreferences()
        except Exception:
            logger.exception("Failed to read memory.json at %s", self._memory_json_path)
            return UserInterests(), [], EngagementPreferences()

        interests = UserInterests(
            topics=data.get("interests", {}).get("topics", []),
            keywords=data.get("interests", {}).get("keywords", []),
            negative_topics=data.get("interests", {}).get("negative_topics", []),
        )

        people = []
        for p in data.get("tracked_people", []):
            people.append(TrackedPerson(
                name=p.get("name", ""),
                handles=p.get("handles", {}),
                reason=p.get("reason", ""),
                priority=p.get("priority", "normal"),
            ))

        eng_data = data.get("engagement", {})
        engagement = EngagementPreferences(
            voice_notes=eng_data.get("voice_notes", ""),
            avoid_topics=eng_data.get("avoid_topics", []),
            style=eng_data.get("style", ""),
        )

        return interests, people, engagement
