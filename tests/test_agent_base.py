"""Tests for BaseAgent and tool framework."""

from __future__ import annotations

import json
import sqlite3

from blah.agents.base import BaseAgent
from blah.agents.tools.base import ToolRegistry, ToolResult, collect_tools, tool
from blah.config.settings import BlahSettings
from tests.mocks.llm import MockLLMClient


class SimpleAgent(BaseAgent):
    """Minimal agent for testing."""

    @tool(
        name="echo",
        description="Echo the input back.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(self, text: str) -> ToolResult:
        return ToolResult(content=json.dumps({"echoed": text}))

    def system_prompt(self) -> str:
        return "You are a test agent."


def test_tool_decorator():
    """@tool decorator attaches metadata to functions."""

    @tool(name="test", description="A test", parameters={"type": "object", "properties": {}})
    def my_func():
        pass

    assert my_func._tool_name == "test"
    assert my_func._tool_description == "A test"


def test_collect_tools():
    """collect_tools finds decorated methods on an object."""

    class Holder:
        @tool(name="foo", description="Foo", parameters={"type": "object", "properties": {}})
        def foo(self) -> ToolResult:
            return ToolResult(content="ok")

        def not_a_tool(self):
            pass

    tools = collect_tools(Holder())
    assert len(tools) == 1
    assert tools[0].name == "foo"


def test_tool_registry():
    registry = ToolRegistry()

    class Holder:
        @tool(name="bar", description="Bar", parameters={"type": "object", "properties": {}})
        def bar(self) -> ToolResult:
            return ToolResult(content="ok")

    for td in collect_tools(Holder()):
        registry.register(td)

    assert len(registry) == 1
    assert registry.get("bar") is not None
    assert registry.get("nonexistent") is None
    schemas = registry.list_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "bar"


def test_base_agent_registers_tools(db: sqlite3.Connection, settings: BlahSettings):
    mock_llm = MockLLMClient()
    agent = SimpleAgent(mock_llm, db, settings)
    assert len(agent.tool_registry) == 1
    assert agent.tool_registry.get("echo") is not None


def test_execute_tool(db: sqlite3.Connection, settings: BlahSettings):
    mock_llm = MockLLMClient()
    agent = SimpleAgent(mock_llm, db, settings)
    result = agent._execute_tool("echo", {"text": "hello"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["echoed"] == "hello"


def test_execute_unknown_tool(db: sqlite3.Connection, settings: BlahSettings):
    mock_llm = MockLLMClient()
    agent = SimpleAgent(mock_llm, db, settings)
    result = agent._execute_tool("nonexistent", {})
    assert result.is_error
    assert "Unknown tool" in result.content


def test_agent_loop_text_only(db: sqlite3.Connection, settings: BlahSettings):
    """Agent loop with a simple text response (no tool use)."""
    mock_llm = MockLLMClient()
    mock_llm.add_response(text="Hello there!")

    agent = SimpleAgent(mock_llm, db, settings)
    messages = [{"role": "user", "content": "Hi"}]
    result = agent._agent_loop(messages, agent.tool_registry.list_schemas())

    assert len(result) == 2  # user + assistant
    assert result[1]["role"] == "assistant"
    assert len(mock_llm.calls) == 1


def test_agent_loop_with_tool_use(db: sqlite3.Connection, settings: BlahSettings):
    """Agent loop: LLM calls a tool, then responds with text."""
    mock_llm = MockLLMClient()
    # First response: tool call
    mock_llm.add_response(
        tool_use={"name": "echo", "id": "call_1", "input": {"text": "test"}},
    )
    # Second response: text after tool result
    mock_llm.add_response(text="I echoed: test")

    agent = SimpleAgent(mock_llm, db, settings)
    messages = [{"role": "user", "content": "Echo test"}]
    result = agent._agent_loop(messages, agent.tool_registry.list_schemas())

    # user, assistant (tool_use), user (tool_result), assistant (text)
    assert len(result) == 4
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "user"
    assert result[2]["content"][0]["type"] == "tool_result"
    assert result[3]["role"] == "assistant"
    assert len(mock_llm.calls) == 2


def test_truncate_history(db: sqlite3.Connection, settings: BlahSettings):
    mock_llm = MockLLMClient()
    agent = SimpleAgent(mock_llm, db, settings)
    agent.max_history_messages = 5

    messages = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    truncated = agent._truncate_history(messages)
    assert len(truncated) == 5
    assert truncated[0]["content"] == "msg 5"


def test_system_prompt(db: sqlite3.Connection, settings: BlahSettings):
    mock_llm = MockLLMClient()
    agent = SimpleAgent(mock_llm, db, settings)
    assert agent.system_prompt() == "You are a test agent."
