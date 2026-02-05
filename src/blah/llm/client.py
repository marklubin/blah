"""Thin wrapper around the Anthropic SDK."""

from __future__ import annotations

import os

import anthropic


class LLMClient:
    """Synchronous Anthropic API client for tool-use conversations."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or "claude-sonnet-4-5"
        self._client = anthropic.Anthropic(api_key=self.api_key)

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
