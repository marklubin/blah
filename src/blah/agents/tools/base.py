"""Tool framework: @tool decorator, ToolResult, registry helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result returned by a tool execution."""

    content: str
    is_error: bool = False


@dataclass
class ToolDef:
    """A registered tool with its Anthropic schema and handler function."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., ToolResult]

    def to_anthropic_schema(self) -> dict:
        """Convert to Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ToolRegistry:
    """Registry of tools available to an agent."""

    _tools: dict[str, ToolDef] = field(default_factory=dict)

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_schemas(self) -> list[dict]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable:
    """Decorator that attaches Anthropic tool schema metadata to a function.

    Usage:
        @tool(
            name="set_title",
            description="Set the rant title",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string", "description": "The title"}},
                "required": ["title"],
            },
        )
        def set_title(self, title: str) -> ToolResult:
            ...
    """

    def decorator(func: Callable) -> Callable:
        func._tool_name = name  # noqa: B010
        func._tool_description = description  # noqa: B010
        func._tool_parameters = parameters  # noqa: B010
        return func

    return decorator


def collect_tools(obj: object) -> list[ToolDef]:
    """Scan an object for methods decorated with @tool and return ToolDef list."""
    tools = []
    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue
        method = getattr(obj, attr_name, None)
        if callable(method) and hasattr(method, "_tool_name"):
            tools.append(
                ToolDef(
                    name=method._tool_name,
                    description=method._tool_description,
                    parameters=method._tool_parameters,
                    handler=method,
                )
            )
    return tools
