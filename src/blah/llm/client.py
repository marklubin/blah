"""Thin wrapper around the Anthropic SDK."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class StreamedResponse:
    """Accumulated response from streaming."""

    text: str = ""
    tool_uses: list[dict] = field(default_factory=list)
    stop_reason: str | None = None

    def to_content_blocks(self) -> list[dict]:
        """Convert to message content blocks for history."""
        blocks = []
        if self.text:
            blocks.append({"type": "text", "text": self.text})
        for tool in self.tool_uses:
            blocks.append({
                "type": "tool_use",
                "id": tool["id"],
                "name": tool["name"],
                "input": tool["input"],
            })
        return blocks


class LLMClient:
    """Synchronous Anthropic API client for tool-use conversations."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or "claude-sonnet-4-5"
        self._client = anthropic.Anthropic(api_key=self.api_key)
        logger.info("LLMClient initialized with model: %s", self.model)

    def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """Send a messages request, optionally with tools."""
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        return self._client.messages.create(**kwargs)

    def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> Iterator[tuple[str, StreamedResponse]]:
        """Stream a messages request, yielding (event_type, accumulated_response).

        event_type is one of: "text_delta", "tool_use", "done"
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = StreamedResponse()
        current_tool: dict | None = None

        logger.debug("Starting streaming request to %s", self.model)
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        current_tool = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": "",
                        }

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        response.text += event.delta.text
                        yield ("text_delta", response)
                    elif event.delta.type == "input_json_delta":
                        if current_tool:
                            current_tool["input"] += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if current_tool:
                        # Parse the accumulated JSON input
                        import json
                        try:
                            current_tool["input"] = json.loads(current_tool["input"])
                        except json.JSONDecodeError:
                            current_tool["input"] = {}
                        response.tool_uses.append(current_tool)
                        yield ("tool_use", response)
                        current_tool = None

                elif event.type == "message_stop":
                    pass

                elif event.type == "message_delta" and hasattr(event.delta, "stop_reason"):
                    response.stop_reason = event.delta.stop_reason

        yield ("done", response)
