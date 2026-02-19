"""Memory provider interface — structured context for agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class UserInterests:
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    negative_topics: list[str] = field(default_factory=list)


@dataclass
class TrackedPerson:
    name: str
    handles: dict[str, str] = field(default_factory=dict)  # platform -> handle
    reason: str = ""
    priority: str = "normal"  # "high", "normal", "low"


@dataclass
class EngagementPreferences:
    voice_notes: str = ""
    avoid_topics: list[str] = field(default_factory=list)
    style: str = ""


@dataclass
class MemoryContext:
    interests: UserInterests = field(default_factory=UserInterests)
    tracked_people: list[TrackedPerson] = field(default_factory=list)
    engagement: EngagementPreferences = field(default_factory=EngagementPreferences)
    raw_context: str = ""

    def to_prompt_text(self) -> str:
        """Format all context into a single string for LLM prompt injection."""
        parts = []

        if self.raw_context:
            parts.append(self.raw_context)

        if self.interests.topics:
            parts.append("\n## Topics of Interest")
            for topic in self.interests.topics:
                parts.append(f"- {topic}")

        if self.interests.keywords:
            parts.append("\n## Keywords to Watch")
            parts.append(", ".join(self.interests.keywords))

        if self.interests.negative_topics:
            parts.append("\n## Topics to Avoid")
            for topic in self.interests.negative_topics:
                parts.append(f"- {topic}")

        if self.tracked_people:
            parts.append("\n## Tracked People")
            for person in self.tracked_people:
                handles_str = ", ".join(f"{p}: @{h}" for p, h in person.handles.items())
                line = f"- **{person.name}** ({handles_str})"
                if person.reason:
                    line += f" — {person.reason}"
                if person.priority != "normal":
                    line += f" [{person.priority}]"
                parts.append(line)

        if self.engagement.voice_notes:
            parts.append(f"\n## Voice & Style\n{self.engagement.voice_notes}")

        if self.engagement.style:
            parts.append(f"\n## Engagement Style\n{self.engagement.style}")

        if self.engagement.avoid_topics:
            parts.append("\n## Avoid These Topics")
            for topic in self.engagement.avoid_topics:
                parts.append(f"- {topic}")

        return "\n".join(parts)


@runtime_checkable
class MemoryProvider(Protocol):
    """Interface for providing structured memory context."""

    def get_context(self) -> MemoryContext: ...
    def refresh(self) -> None: ...
