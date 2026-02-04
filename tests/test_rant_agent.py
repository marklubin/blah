"""Tests for RantAgent and rant tools."""

from __future__ import annotations

import json
import sqlite3

from blah.agents.rant import RantAgent
from blah.config.settings import BlahSettings
from blah.db.repository import PieceRepo, RantRepo
from tests.mocks.llm import MockLLMClient


def _make_agent(
    db: sqlite3.Connection, settings: BlahSettings, rant_id: str
) -> tuple[RantAgent, MockLLMClient]:
    mock_llm = MockLLMClient()
    agent = RantAgent(mock_llm, db, settings, rant_id)
    return agent, mock_llm


def test_rant_agent_has_tools(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    tool_names = {t.name for t in agent.tool_registry._tools.values()}
    assert "set_title" in tool_names
    assert "set_summary" in tool_names
    assert "create_piece" in tool_names
    assert "update_piece" in tool_names
    assert "finalize_rant" in tool_names
    assert "attach_resource" in tool_names
    assert "suggest_context_update" in tool_names


def test_set_title(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    result = agent._execute_tool("set_title", {"title": "My Rant"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["title"] == "My Rant"
    # Verify persisted
    assert RantRepo(db).get(rant["id"])["title"] == "My Rant"


def test_set_summary(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    result = agent._execute_tool("set_summary", {"summary": "About AI agents"})
    assert not result.is_error
    assert RantRepo(db).get(rant["id"])["summary"] == "About AI agents"


def test_create_piece(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    result = agent._execute_tool(
        "create_piece",
        {"platform": "bluesky", "content": "Hello from blah!"},
    )
    assert not result.is_error
    data = json.loads(result.content)
    assert data["platform"] == "bluesky"
    assert data["status"] == "draft"

    pieces = PieceRepo(db).list_by_rant(rant["id"])
    assert len(pieces) == 1
    assert pieces[0]["content"] == "Hello from blah!"


def test_update_piece(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])

    # Create then update
    agent._execute_tool("create_piece", {"platform": "twitter", "content": "v1"})
    pieces = PieceRepo(db).list_by_rant(rant["id"])
    piece_id = pieces[0]["id"]

    result = agent._execute_tool("update_piece", {"piece_id": piece_id, "content": "v2"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["content"] == "v2"


def test_update_piece_wrong_rant(db: sqlite3.Connection, settings: BlahSettings):
    rant1 = RantRepo(db).create()
    rant2 = RantRepo(db).create()

    # Create piece on rant2
    PieceRepo(db).create(rant_id=rant2["id"], platform="bluesky", content="other")
    pieces = PieceRepo(db).list_by_rant(rant2["id"])
    piece_id = pieces[0]["id"]

    # Try to update from agent bound to rant1
    agent, _ = _make_agent(db, settings, rant1["id"])
    result = agent._execute_tool("update_piece", {"piece_id": piece_id, "content": "hacked"})
    assert result.is_error
    assert "does not belong" in result.content


def test_finalize_rant(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])

    agent._execute_tool("create_piece", {"platform": "bluesky", "content": "Post 1"})
    agent._execute_tool("create_piece", {"platform": "twitter", "content": "Post 2"})

    result = agent._execute_tool("finalize_rant", {})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["status"] == "active"
    assert data["pieces_approved"] == 2

    # Verify rant status
    assert RantRepo(db).get(rant["id"])["status"] == "active"

    # Verify all pieces approved
    pieces = PieceRepo(db).list_by_rant(rant["id"])
    assert all(p["status"] == "approved" for p in pieces)


def test_attach_resource(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    result = agent._execute_tool(
        "attach_resource",
        {"path_or_url": "https://example.com/img.png", "resource_type": "image"},
    )
    assert not result.is_error
    data = json.loads(result.content)
    assert data["type"] == "image"
    assert data["location"] == "https://example.com/img.png"


def test_suggest_context_update(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    result = agent._execute_tool(
        "suggest_context_update",
        {"suggestion": "User prefers technical tone"},
    )
    assert not result.is_error

    # Check context.md was updated
    ctx = settings.context_path.read_text()
    assert "User prefers technical tone" in ctx


def test_system_prompt_new_rant(db: sqlite3.Connection, settings: BlahSettings):
    rant = RantRepo(db).create()
    agent, _ = _make_agent(db, settings, rant["id"])
    prompt = agent.system_prompt()
    assert "Blah Rant Agent" in prompt
    assert "New rant" in prompt


def test_system_prompt_with_state(db: sqlite3.Connection, settings: BlahSettings):
    repo = RantRepo(db)
    rant = repo.create(title="Test Rant", summary="About testing")
    PieceRepo(db).create(rant_id=rant["id"], platform="bluesky", content="Hello!")

    agent, _ = _make_agent(db, settings, rant["id"])
    prompt = agent.system_prompt()
    assert "Test Rant" in prompt
    assert "About testing" in prompt
    assert "bluesky" in prompt


def test_agent_loop_with_tool(db: sqlite3.Connection, settings: BlahSettings):
    """Full agent loop: LLM sets title via tool, then responds."""
    rant = RantRepo(db).create()
    agent, mock_llm = _make_agent(db, settings, rant["id"])

    mock_llm.add_response(
        tool_use={"name": "set_title", "id": "call_1", "input": {"title": "AI Agents"}},
    )
    mock_llm.add_response(text="I've set the title to 'AI Agents'.")

    messages = [{"role": "user", "content": "Create a rant about AI agents"}]
    result = agent._agent_loop(messages, agent.tool_registry.list_schemas())

    assert len(result) == 4
    assert RantRepo(db).get(rant["id"])["title"] == "AI Agents"
