# Plan: Blah MVP Technical Implementation

## Overview

Implement the Blah MVP as a Python CLI tool using uv for package management, with comprehensive testing and observability from day one.

## Project Structure

```
blah/
├── src/
│   └── blah/
│       ├── __init__.py
│       ├── __main__.py              # python -m blah
│       ├── py.typed                 # PEP 561 type marker
│       │
│       ├── cli/                     # CLI Layer
│       │   ├── __init__.py
│       │   ├── main.py              # Click entry point
│       │   └── commands/
│       │       ├── __init__.py
│       │       ├── rant.py
│       │       ├── radar.py
│       │       ├── config.py
│       │       ├── context.py
│       │       └── stats.py
│       │
│       ├── agents/                  # Agent Layer
│       │   ├── __init__.py
│       │   ├── base.py              # Base agent class
│       │   ├── rant.py
│       │   ├── radar_config.py
│       │   ├── radar_report.py
│       │   ├── context_manager.py
│       │   ├── research.py          # Non-interactive
│       │   └── tools/
│       │       ├── __init__.py
│       │       ├── base.py          # @logged_tool decorator
│       │       ├── rant_tools.py
│       │       ├── radar_tools.py
│       │       └── context_tools.py
│       │
│       ├── services/                # Business Logic
│       │   ├── __init__.py
│       │   ├── publishing.py
│       │   └── pipeline.py          # poll → triage → research → report
│       │
│       ├── adapters/                # External Integrations
│       │   ├── __init__.py
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── base.py          # LLM client protocol
│       │   │   ├── anthropic.py
│       │   │   └── openai.py
│       │   ├── platforms/
│       │   │   ├── __init__.py
│       │   │   ├── base.py          # PlatformAdapter ABC
│       │   │   ├── bluesky.py
│       │   │   ├── mastodon.py
│       │   │   └── twitter.py
│       │   └── db/
│       │       ├── __init__.py
│       │       ├── connection.py
│       │       ├── schema.sql
│       │       └── repository.py
│       │
│       ├── models/                  # Domain Models (Pydantic)
│       │   ├── __init__.py
│       │   ├── rant.py
│       │   ├── piece.py
│       │   ├── source.py
│       │   ├── feed_item.py
│       │   ├── report.py
│       │   └── config.py
│       │
│       ├── observability/           # Logging & Metrics
│       │   ├── __init__.py
│       │   ├── logging_setup.py     # structlog config
│       │   ├── context.py           # log context binding
│       │   ├── tracing.py           # correlation IDs
│       │   ├── llm_metrics.py       # token/cost tracking
│       │   ├── metrics_store.py     # SQLite queries
│       │   └── errors.py            # error categorization
│       │
│       └── config/
│           ├── __init__.py
│           └── settings.py          # Pydantic settings
│
├── tests/
│   ├── conftest.py                  # Global fixtures
│   ├── factories.py                 # Test data factories
│   ├── mocks/
│   │   ├── __init__.py
│   │   ├── llm.py                   # MockLLMClient
│   │   └── adapters.py              # MockPlatformAdapter
│   ├── fixtures/
│   │   ├── context_samples/
│   │   └── llm_responses/
│   ├── unit/
│   │   ├── agents/
│   │   ├── adapters/
│   │   └── services/
│   └── integration/
│       ├── test_agent_loops.py
│       └── test_cli_commands.py
│
├── pyproject.toml
├── uv.lock
├── .python-version
└── README.md
```

## pyproject.toml

```toml
[project]
name = "blah"
version = "0.1.0"
description = "Social engagement agent CLI"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # CLI
    "click>=8.1",
    "rich>=13.0",
    "prompt-toolkit>=3.0",

    # LLM
    "anthropic>=0.40",
    "openai>=1.0",

    # Platforms
    "atproto>=0.0.50",
    "Mastodon.py>=1.8",
    "tweepy>=4.14",

    # Config & Validation
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",

    # HTTP
    "httpx>=0.27",

    # Observability
    "structlog>=24.0",
]

[project.scripts]
blah = "blah.cli.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/blah"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "responses>=0.25",
    "ruff>=0.5",
    "mypy>=1.10",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=blah --cov-report=term-missing"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
```

## Implementation Phases

### Phase 1: Foundation (Files: 15)

1. **Project setup**
   - `uv init blah --package --python ">=3.12"`
   - Create directory structure
   - Configure pyproject.toml

2. **Core infrastructure**
   - `src/blah/config/settings.py` - Pydantic settings with env var loading
   - `src/blah/adapters/db/schema.sql` - SQLite schema from design doc
   - `src/blah/adapters/db/connection.py` - Connection management, init
   - `src/blah/adapters/db/repository.py` - CRUD operations

3. **Observability setup**
   - `src/blah/observability/logging_setup.py` - structlog config
   - `src/blah/observability/context.py` - log context binding
   - `src/blah/observability/errors.py` - error categorization

4. **CLI skeleton**
   - `src/blah/cli/main.py` - Click group with all commands stubbed
   - `src/blah/cli/commands/*.py` - Empty command files

5. **Test infrastructure**
   - `tests/conftest.py` - DB fixtures, mock fixtures
   - `tests/factories.py` - Entity factories

**Verification:**
```bash
uv run blah --help           # CLI works
uv run blah init             # Creates ~/.blah/
uv run pytest tests/         # Tests pass
```

### Phase 2: Models & Persistence (Files: 10)

1. **Domain models** (Pydantic)
   - `src/blah/models/rant.py` - Rant, Piece, Resource
   - `src/blah/models/source.py` - Source with platform-specific config
   - `src/blah/models/feed_item.py` - FeedItem with status
   - `src/blah/models/report.py` - Report, ReportItem
   - `src/blah/models/config.py` - Config schema

2. **Repository implementation**
   - CRUD for all entities
   - Chat history persistence
   - Indexed queries for FeedItems

3. **Tests**
   - Unit tests for all repository methods
   - Factory tests

**Verification:**
```bash
uv run pytest tests/unit/adapters/db/
```

### Phase 3: LLM Client (Files: 8)

1. **LLM abstraction**
   - `src/blah/adapters/llm/base.py` - Protocol for LLM clients
   - `src/blah/adapters/llm/anthropic.py` - Anthropic implementation
   - `src/blah/observability/llm_metrics.py` - Token/cost tracking

2. **Agent base class**
   - `src/blah/agents/base.py` - Base agent with tool execution loop
   - `src/blah/agents/tools/base.py` - @logged_tool decorator

3. **Test mocks**
   - `tests/mocks/llm.py` - MockLLMClient, ScriptedLLMClient

**Verification:**
```bash
uv run pytest tests/unit/adapters/llm/
# Manual: Test with real API key
```

### Phase 4: Rant Flow (Files: 10)

1. **Rant Agent**
   - `src/blah/agents/rant.py` - Agent implementation
   - `src/blah/agents/tools/rant_tools.py` - Tool implementations
   - `src/blah/services/publishing.py` - Publish orchestration

2. **Bluesky Adapter**
   - `src/blah/adapters/platforms/base.py` - PlatformAdapter ABC
   - `src/blah/adapters/platforms/bluesky.py` - atproto implementation

3. **CLI commands**
   - `src/blah/cli/commands/rant.py` - create, list, chat, publish, etc.

4. **Tests**
   - Unit tests for tools
   - Integration test for agent loop with mocked LLM
   - CLI tests with Click runner

**Verification:**
```bash
uv run blah rant create      # Chat works
uv run blah rant list        # Shows rants
uv run blah rant publish 1   # Posts to Bluesky (with real creds)
```

### Phase 5: Radar Flow (Files: 12)

1. **Radar Agents**
   - `src/blah/agents/radar_config.py`
   - `src/blah/agents/radar_report.py`
   - `src/blah/agents/research.py` - Non-interactive enrichment
   - `src/blah/agents/tools/radar_tools.py`

2. **Pipeline**
   - `src/blah/services/pipeline.py` - poll → triage → research → report

3. **CLI commands**
   - `src/blah/cli/commands/radar.py` - config, pull, report, status

**Verification:**
```bash
uv run blah radar config     # Configure sources
uv run blah radar pull       # Fetch and triage items
uv run blah radar report     # Review report
```

### Phase 6: Context Manager & More Adapters (Files: 8)

1. **Context Manager Agent**
   - `src/blah/agents/context_manager.py`
   - `src/blah/agents/tools/context_tools.py`

2. **Additional Adapters**
   - `src/blah/adapters/platforms/mastodon.py`
   - `src/blah/adapters/platforms/twitter.py`

3. **CLI**
   - `src/blah/cli/commands/context.py`

**Verification:**
```bash
uv run blah context show
# Test cross-platform publishing
```

### Phase 7: Stats & Polish (Files: 5)

1. **Metrics & Stats**
   - `src/blah/observability/metrics_store.py`
   - `src/blah/cli/commands/stats.py`

2. **Error handling polish**
   - Consistent user-facing error messages
   - Retry logic for retriable errors

3. **Full test coverage**
   - Integration tests for all flows
   - Edge cases

**Verification:**
```bash
uv run blah stats summary
uv run pytest --cov-report=html  # Check coverage
```

## Testing Strategy

### Unit Tests
- **Agent tools** - Test without LLM, pure function testing
- **Adapters** - Mock HTTP with `responses` library
- **Repository** - In-memory SQLite
- **Coverage target**: 80%+ for tools, adapters, repository

### Integration Tests
- **Agent loops** - Scripted LLM mock returns pre-defined responses
- **CLI commands** - Click's CliRunner
- **Pipeline** - Full poll→report with mocked adapters

### Fixtures
- `tests/factories.py` - RantFactory, PieceFactory, FeedItemFactory, LLMResponseFactory
- `tests/fixtures/context_samples/` - Sample context.md files
- `tests/fixtures/llm_responses/` - Scripted conversation flows

## Observability

### Logging (structlog)
- Console: human-readable with colors (INFO default)
- File: JSON or key-value in `~/.blah/logs/`
- Context binding for agent_id, rant_id, correlation_id

### Metrics (SQLite tables)
- `llm_requests` - token usage, cost, latency
- `platform_operations` - success/failure, latency
- `pipeline_metrics_daily` - aggregated pipeline stats

### CLI Stats
```bash
blah stats summary    # Usage overview
blah stats errors     # Recent errors
blah stats cost       # Cost breakdown
```

## Key Files to Create First

1. `pyproject.toml` - Project config, dependencies, entry point
2. `src/blah/config/settings.py` - Settings with Pydantic
3. `src/blah/adapters/db/schema.sql` - Full SQLite schema
4. `src/blah/observability/logging_setup.py` - structlog setup
5. `src/blah/cli/main.py` - Click entry point
6. `tests/conftest.py` - Core fixtures
7. `src/blah/agents/base.py` - Base agent class
8. `src/blah/adapters/platforms/base.py` - Platform adapter ABC

## Commands to Initialize

```bash
# Create project
cd /home/mark/blah
uv init --package --python ">=3.12"

# Add dependencies
uv add click rich prompt-toolkit anthropic openai atproto Mastodon.py tweepy pydantic pydantic-settings pyyaml httpx structlog

# Add dev dependencies
uv add --group dev pytest pytest-asyncio pytest-cov responses ruff mypy

# Create structure
mkdir -p src/blah/{cli/commands,agents/tools,services,adapters/{llm,platforms,db},models,observability,config}
mkdir -p tests/{unit/{agents,adapters,services},integration,mocks,fixtures/{context_samples,llm_responses}}

# Type marker
touch src/blah/py.typed

# Verify
uv run blah --help
uv run pytest
```
