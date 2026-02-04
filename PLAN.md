# Blah MVP Build Plan

5 phases. Each phase = a PR to GitHub. Wait for review before starting next phase.

## Workflow
- Each phase is implemented on a feature branch and submitted as a PR
- Wait for feedback/approval before proceeding to the next phase
- DEFERRED.md explicitly tracks deferred features

## Key Simplifications

- **5 phases instead of 7** — compressed foundation, user value from Phase 2
- **Synchronous throughout** — no async, no task queue (deferred post-MVP)
- **No LLM abstraction layer** — Anthropic directly, extract abstraction when second provider is needed
- **`input()` + Rich for chat** — no prompt_toolkit (add later for polish)
- **`db/` not `adapters/db/`** — SQLite is the persistence layer, not a swappable adapter
- **`llm/` not `adapters/llm/`** — single provider, no abstraction
- **Observability deferred to Phase 5** — structlog + metrics after system is stable
- **Research Agent simplified** — single-pass triage in Phase 4, not full generator-critic
- **Keep `uv_build`** — matches pyproject.toml
- **Platform order: Bluesky → Twitter** — Mastodon deferred
- **Alembic for schema migrations** — not raw SQL scripts
- **Models: Claude 4.5 variants** — sonnet-4-5 for conversation, haiku-4-5 for triage/research

## Completed Phases

### Phase 1: Skeleton + Persistence + Init ✓

Merged. CLI skeleton, Alembic migrations, config loading, repository CRUD, 21 tests.

---

## Phase 2: Agent Framework + Rant Agent

**Goal**: `blah rant create` starts a real chat loop with Claude. Agent uses tools to create rants with pieces. `blah rant list` and `blah rant show <id>` work.

**Branch**: `phase-2-rant-agent`
**Dependencies to add**: anthropic

**Files to create**:
```
src/blah/agents/__init__.py
src/blah/agents/base.py           # BaseAgent — THE critical file
src/blah/agents/rant.py           # RantAgent: system prompt, tool registration
src/blah/agents/tools/__init__.py
src/blah/agents/tools/base.py     # @tool decorator, ToolResult type, tool registry
src/blah/agents/tools/rant_tools.py    # set_title, set_summary, create_piece, update_piece, finalize_rant, attach_resource
src/blah/agents/tools/context_tools.py # suggest_context_update (simple: append to context.md)
src/blah/cli/chat.py              # Shared chat loop: input() + Rich console
src/blah/llm/__init__.py
src/blah/llm/client.py            # Thin Anthropic SDK wrapper
tests/mocks/llm.py                # MockLLMClient with scripted responses
tests/test_agent_base.py
tests/test_rant_agent.py
tests/test_rant_cli.py
```

**Update**: `cli/commands/rant.py` (implement create/list/show/chat), `db/repository.py` (complete CRUD)

**BaseAgent design** (`agents/base.py`):
- `__init__(llm_client, db, settings)` — stores deps, initializes tool registry
- `system_prompt() -> str` — subclasses override, injects context.md
- `register_tool(func, schema)` — register tool with Anthropic-format schema
- `run_chat(chat_key)` — main loop: load history → user input → Anthropic messages.create with tools → execute tool_use blocks → display text → save history
- `_execute_tool(name, input) -> str` — dispatch to registered tool
- `max_history_messages` — truncate old messages to control context growth

**Tool pattern** (`agents/tools/base.py`):
- `@tool(name, description, parameters)` decorator attaches Anthropic tool schema to function
- Each tool returns `ToolResult(content, is_error)`

**Conversation loop**: Standard Anthropic tool use — send messages+tools, if stop_reason=="tool_use" execute and loop, if "end_turn" display and wait for input.

---

## Phase 3: Publishing + Bluesky Adapter

**Goal**: `blah rant publish <id>` posts to Bluesky. First complete end-to-end flow. Also `blah context show/edit`.

**Branch**: `phase-3-bluesky-publishing`
**Dependencies to add**: atproto

**Files to create**:
```
src/blah/adapters/__init__.py
src/blah/adapters/base.py         # PlatformAdapter ABC (post, reply, read, follow, fetch_feed) — synchronous
src/blah/adapters/bluesky.py      # BlueskyAdapter using atproto
src/blah/services/__init__.py
src/blah/services/publishing.py   # PublishService: iterate approved pieces, call adapter, update status
tests/test_publishing.py
tests/test_bluesky_adapter.py
tests/mocks/adapters.py           # MockPlatformAdapter
```

**Update**: `cli/commands/rant.py` (publish/delete/failures/retry/mark-posted), `cli/commands/context.py` (show/edit), `db/repository.py` (piece status updates, failure tracking)

**Piece status flow**: draft → approved (on finalize_rant) → publishing → published/failed

---

## Phase 4: Radar Flow

**Goal**: `blah radar config` configures sources, `blah radar pull` fetches+triages+generates report, `blah radar report` reviews via chat.

**Branch**: `phase-4-radar`
**No new dependencies** — reuses Bluesky adapter for feed fetching.

**Files to create**:
```
src/blah/agents/radar_config.py
src/blah/agents/radar_report.py
src/blah/agents/tools/radar_tools.py
src/blah/models/source.py
src/blah/models/feed_item.py
src/blah/models/report.py
src/blah/services/pipeline.py    # poll_sources → triage_items → generate_report
src/blah/services/triage.py      # batch score items with Haiku against context.md
tests/test_radar_config.py
tests/test_radar_report.py
tests/test_pipeline.py
tests/test_triage.py
```

**Update**: `cli/commands/radar.py`, `db/repository.py` (SourceRepo, FeedItemRepo, ReportRepo, ReportItemRepo), `adapters/bluesky.py` (add fetch_feed)

**Pipeline**: `run()` does poll → triage → generate report, all synchronous.
**Triage**: send batches of items + context.md to Haiku, score 0.0-1.0, items above 0.3 threshold pass.

---

## Phase 5: Context Manager + Twitter + Polish

**Goal**: Smart context.md updates via Context Manager Agent. Twitter adapter (second platform). Structured logging. Config commands.

**Branch**: `phase-5-context-twitter-polish`
**Dependencies to add**: twitterapi.io client (httpx for REST calls), xdk (official X SDK for writes), structlog

### Twitter/X API Strategy

**Split approach to control costs:**
- **Reads** (feed fetching, post reading, search): **twitterapi.io** — third-party proxy, cheaper for high-volume read operations
- **Writes** (posting, replying, following): **Official X API via xdk** — required for write operations, ensures compliance

The TwitterAdapter will internally route to the appropriate client based on operation type. Both clients share the same credential configuration.

**Files to create**:
```
src/blah/agents/context_manager.py     # Non-interactive agent, uses Opus 4.5
src/blah/adapters/twitter.py           # TwitterAdapter: reads via twitterapi.io, writes via xdk
src/blah/adapters/cache.py             # API response cache (SQLite-backed)
src/blah/observability/__init__.py
src/blah/observability/logging.py      # structlog setup
src/blah/observability/llm_metrics.py  # token/cost tracking to SQLite
tests/test_context_manager.py
tests/test_twitter_adapter.py
tests/test_llm_metrics.py
```

**Update**: `cli/commands/config.py`, `agents/tools/context_tools.py`, `db/` (new migration for llm_requests + api_cache tables), `db/repository.py` (LLMMetricsRepo), `llm/client.py` (token counting)

**X API Cache** (`adapters/cache.py`):
SQLite-backed cache for all X API read operations.
- Cache table in new Alembic migration
- TTL configurable per operation type (feed: 5min, post read: 1hr, profile: 24hr)
- Write operations never cached

**Context Manager Agent**: non-interactive, invoked synchronously by other agents via `suggest_context_update()`. Uses Opus 4.5.

---

## Critical Path

Phase 1 ✓ → Phase 2 → Phase 3 → Phase 4 → Phase 5

Phase 2 (`agents/base.py`) is the architectural linchpin — every agent depends on it.
Phase 3 (`adapters/base.py`) defines the platform contract — all adapters implement it.

## Risk Mitigations

- **Chat history growth**: BaseAgent `max_history_messages` to truncate old messages
- **Context.md token counting**: word-count heuristic (~0.75 words/token) or `anthropic.count_tokens()`
- **Triage cost**: batch items 20-30 per Haiku call
- **atproto SDK instability**: pin version, adapter layer isolates breakage
- **twitterapi.io reliability**: cache aggressively, fallback gracefully on errors
