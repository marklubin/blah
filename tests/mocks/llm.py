"""Mock LLM client for testing agents without real API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class MockToolUseBlock:
    type: str = "tool_use"
    id: str = "tool_1"
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class MockMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


class MockLLMClient:
    """LLM client that returns scripted responses for testing.

    Usage:
        mock = MockLLMClient()
        mock.add_response(text="Hello!")
        mock.add_response(tool_use={"name": "set_title", "input": {"title": "Test"}})
        mock.add_response(text="Done setting the title.")
    """

    def __init__(self, model: str = "mock-model"):
        self.model = model
        self.api_key = "mock-key"
        self._responses: list[MockMessage] = []
        self._call_count = 0
        self.calls: list[dict[str, Any]] = []

    def add_response(
        self,
        text: str | None = None,
        tool_use: dict | None = None,
        stop_reason: str | None = None,
    ) -> None:
        """Queue a response. If tool_use is provided, stop_reason defaults to 'tool_use'."""
        content = []
        if text:
            content.append(MockTextBlock(text=text))
        if tool_use:
            content.append(
                MockToolUseBlock(
                    id=tool_use.get("id", f"tool_{self._call_count + len(self._responses)}"),
                    name=tool_use["name"],
                    input=tool_use.get("input", {}),
                )
            )
        if stop_reason is None:
            stop_reason = "tool_use" if tool_use else "end_turn"
        self._responses.append(MockMessage(content=content, stop_reason=stop_reason))

    def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> MockMessage:
        """Return the next scripted response."""
        self.calls.append({
            "messages": messages,
            "system": system,
            "tools": tools,
            "max_tokens": max_tokens,
        })
        if self._call_count >= len(self._responses):
            return MockMessage(
                content=[MockTextBlock(text="(no more scripted responses)")],
                stop_reason="end_turn",
            )
        response = self._responses[self._call_count]
        self._call_count += 1
        return response
