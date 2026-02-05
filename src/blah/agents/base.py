"""BaseAgent — the core agent loop for tool-use conversations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.status import Status

from blah.agents.tools.base import ToolRegistry, ToolResult, collect_tools
from blah.config.settings import BlahSettings
from blah.db.repository import ChatHistoryRepo
from blah.llm.client import LLMClient

console = Console()


class BaseAgent:
    """Base class for all chat agents.

    Subclasses must override `system_prompt()` and decorate methods with @tool.
    """

    max_history_messages: int = 100

    def __init__(
        self,
        llm_client: LLMClient,
        db: sqlite3.Connection,
        settings: BlahSettings,
    ):
        self.llm = llm_client
        self.db = db
        self.settings = settings
        self.chat_history_repo = ChatHistoryRepo(db)
        self.tool_registry = ToolRegistry()

        # Auto-register tools from decorated methods
        for tool_def in collect_tools(self):
            self.tool_registry.register(tool_def)

    def system_prompt(self) -> str:
        """Return the system prompt. Subclasses must override."""
        raise NotImplementedError

    def _load_context(self) -> str:
        """Load context.md contents."""
        ctx_path = self.settings.context_path
        if ctx_path.exists():
            return ctx_path.read_text()
        return ""

    def _truncate_history(self, messages: list[dict]) -> list[dict]:
        """Truncate message history to max_history_messages, keeping recent."""
        if len(messages) <= self.max_history_messages:
            return messages
        return messages[-self.max_history_messages :]

    def run_chat(self, chat_key: str) -> None:
        """Main chat loop: load history, get input, call LLM, execute tools, repeat."""
        messages = self.chat_history_repo.get(chat_key)
        messages = self._truncate_history(messages)

        tools = self.tool_registry.list_schemas()

        # If resuming with history, show a brief note
        if messages:
            console.print("[dim]Resuming conversation...[/dim]\n")

        while True:
            # Get user input
            try:
                console.print()
                user_input = console.input("[bold green]you:[/bold green] ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Ending chat.[/dim]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "/quit", "/exit"):
                console.print("[dim]Ending chat.[/dim]")
                break

            messages.append({"role": "user", "content": user_input})

            # LLM loop: call API, handle tool use, repeat until end_turn
            messages = self._agent_loop(messages, tools)

            # Save after each exchange
            self.chat_history_repo.save(chat_key, messages)

    def _agent_loop(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        """Call LLM, execute any tool calls, loop until end_turn or no tool use."""
        while True:
            with Status("[bold cyan]Thinking...[/bold cyan]", console=console):
                response = self.llm.chat(
                    messages=messages,
                    system=self.system_prompt(),
                    tools=tools if tools else None,
                )

            # Build the assistant message content blocks
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            # Display text blocks
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    console.print()
                    console.print("[bold blue]agent:[/bold blue]")
                    console.print(Markdown(block.text))

            # If no tool use, we're done
            if response.stop_reason != "tool_use":
                break

            # Execute tool calls and add results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._execute_tool(block.name, block.input)
                    console.print(
                        f"  [dim]tool:{block.name} → "
                        f"{'error: ' if result.is_error else ''}"
                        f"{_truncate(result.content, 100)}[/dim]"
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result.content,
                        "is_error": result.is_error,
                    })

            messages.append({"role": "user", "content": tool_results})

        return messages

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Dispatch to a registered tool handler."""
        tool_def = self.tool_registry.get(name)
        if tool_def is None:
            return ToolResult(
                content=json.dumps({"error": f"Unknown tool: {name}"}),
                is_error=True,
            )
        try:
            return tool_def.handler(**tool_input)
        except Exception as e:
            return ToolResult(
                content=json.dumps({"error": str(e)}),
                is_error=True,
            )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
