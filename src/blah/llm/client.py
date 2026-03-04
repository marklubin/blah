"""LLM client supporting Anthropic and OpenAI-compatible providers."""

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


@dataclass
class LLMResponse:
    """Unified response wrapper for both providers."""

    text: str = ""
    stop_reason: str | None = None
    tool_uses: list[dict] = field(default_factory=list)


class LLMClient:
    """LLM client supporting Anthropic and OpenAI-compatible providers."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str = "anthropic",
        base_url: str | None = None,
    ):
        self.model = model or "claude-sonnet-4-5"
        self.provider = provider
        self.base_url = base_url
        self._anthropic_client = None

        if provider == "openai":
            import httpx as _httpx

            # For custom endpoints (Modal, etc.) use httpx directly.
            # base_url should be the full chat completions URL or a standard /v1 base.
            self._http = _httpx.Client(timeout=300.0)
            # If base_url ends with /v1, append /chat/completions; otherwise use as-is
            if base_url and base_url.rstrip("/").endswith("/v1"):
                self._chat_url = base_url.rstrip("/") + "/chat/completions"
            else:
                self._chat_url = base_url
            self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "not-needed")
        else:
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self._anthropic_client = anthropic.Anthropic(api_key=self.api_key)

        logger.info("LLMClient initialized: provider=%s model=%s base_url=%s", provider, self.model, base_url)

    def warmup(self, timeout: float = 300.0, interval: float = 5.0) -> bool:
        """Send a minimal request to warm up the endpoint.

        Retries until the endpoint responds or timeout is reached.
        No-op for Anthropic (always available). Returns True if ready.
        """
        if self.provider != "openai":
            return True

        import time

        start = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._http.post(
                    self._chat_url,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                elapsed = time.monotonic() - start
                logger.info("LLM endpoint warm after %d attempts (%.1fs)", attempt, elapsed)
                return True
            except Exception as e:
                elapsed = time.monotonic() - start
                if elapsed + interval >= timeout:
                    logger.error("LLM endpoint not ready after %d attempts (%.0fs): %s", attempt, elapsed, e)
                    return False
                logger.info("Warmup attempt %d (%.0fs elapsed): %s", attempt, elapsed, e)
                time.sleep(interval)

    def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message | LLMResponse:
        """Send a messages request, optionally with tools."""
        if self.provider == "openai":
            return self._chat_openai(messages, system, max_tokens)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        return self._anthropic_client.messages.create(**kwargs)

    def _chat_openai(
        self,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat via OpenAI-compatible API using httpx, returning a unified response."""
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            content = msg.get("content", "")
            # Anthropic sends content as list of blocks; flatten for OpenAI
            if isinstance(content, list):
                text_parts = [
                    b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = "\n".join(text_parts)
            oai_messages.append({"role": msg["role"], "content": content})

        payload = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        resp = self._http.post(self._chat_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"] or "",
            stop_reason=choice.get("finish_reason"),
        )

    def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> Iterator[tuple[str, StreamedResponse]]:
        """Stream a messages request, yielding (event_type, accumulated_response).

        event_type is one of: "text_delta", "tool_use", "done"
        Only supported for Anthropic provider.
        """
        if self.provider == "openai":
            # Fallback: non-streaming call wrapped as a single yield
            resp = self._chat_openai(messages, system, max_tokens)
            streamed = StreamedResponse(text=resp.text, stop_reason=resp.stop_reason)
            yield ("text_delta", streamed)
            yield ("done", streamed)
            return

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
        with self._anthropic_client.messages.stream(**kwargs) as stream:
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
