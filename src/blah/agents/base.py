"""BaseAgent — the core agent loop for tool-use conversations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

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

            # Display user message in a panel
            console.print()
            console.print(Panel(
                user_input,
                title="[bold green]you[/bold green]",
                title_align="left",
                border_style="green",
                padding=(0, 1),
            ))

            messages.append({"role": "user", "content": user_input})

            # LLM loop: call API, handle tool use, repeat until end_turn
            messages = self._agent_loop(messages, tools)

            # Save after each exchange
            self.chat_history_repo.save(chat_key, messages)

    def _agent_loop(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        """Call LLM with streaming, execute any tool calls, loop until done."""
        while True:
            console.print()

            # Stream the response
            streamed_text = ""
            response = None

            initial_panel = Panel(
                "...",
                title="[bold blue]agent[/bold blue]",
                title_align="left",
                border_style="blue",
                padding=(0, 1),
            )
            with Live(
                initial_panel,
                console=console,
                refresh_per_second=10,
                transient=False,
            ) as live:
                for event_type, resp in self.llm.chat_stream(
                    messages=messages,
                    system=self.system_prompt(),
                    tools=tools if tools else None,
                ):
                    response = resp
                    if event_type == "text_delta":
                        streamed_text = resp.text
                        # Update the live panel with streamed text
                        live.update(Panel(
                            Markdown(streamed_text) if streamed_text else "...",
                            title="[bold blue]agent[/bold blue]",
                            title_align="left",
                            border_style="blue",
                            padding=(0, 1),
                        ))
                    elif event_type == "done":
                        # Final update
                        if streamed_text:
                            live.update(Panel(
                                Markdown(streamed_text),
                                title="[bold blue]agent[/bold blue]",
                                title_align="left",
                                border_style="blue",
                                padding=(0, 1),
                            ))

            # Build the assistant message content blocks
            assistant_content = response.to_content_blocks()
            messages.append({"role": "assistant", "content": assistant_content})

            # If no tool use, we're done
            if response.stop_reason != "tool_use":
                break

            # Execute tool calls and add results
            tool_results = []
            for tool in response.tool_uses:
                result = self._execute_tool(tool["name"], tool["input"])
                error_prefix = "[red]error:[/red] " if result.is_error else ""
                truncated = _truncate(result.content, 200)
                tool_output = f"[dim]{tool['name']}[/dim] → {error_prefix}{truncated}"
                console.print(Panel(
                    tool_output,
                    title="[bold yellow]tool[/bold yellow]",
                    title_align="left",
                    border_style="yellow",
                    padding=(0, 1),
                ))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool["id"],
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
