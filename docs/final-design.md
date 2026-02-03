# Blah MVP - Final Design Document

*Social engagement agent. Makes noise so you don't have to.*

---

## 1. MVP Scope

### In Scope

| Feature | Description |
|---------|-------------|
| **Rant Flow** | Create and refine content via chat, generate platform pieces, manual publish |
| **Radar Config** | Chat-based configuration of sources and interests |
| **Radar Report** | Review generated reports, decide on engagement actions |
| **Research Enrichment** | Research agent enriches items before report generation |
| **Bluesky + Mastodon** | API-based posting and reading |
| **Twitter** | API integration with rate awareness |
| **context.md** | Shared memory across agents (~2000 tokens) |
| **CLI Interface** | Full command set for rant and radar flows |
| **Local Persistence** | SQLite database at `~/.blah/blah.db` |

### Deferred (Post-MVP)

| Feature | Rationale |
|---------|-----------|
| **Reddit integration** | Stricter API approval process, different content style |
| **Threads integration** | Meta business verification overhead |
| **HN integration** | Browser-only, risk of detection |
| **LinkedIn integration** | Enterprise API only, heavy bot detection |
| **Scheduled publishing** | Focus on agent workflow first, add automation later |
| **Background radar polling** | Start with manual `blah radar pull` |
| **Auto-engagement** | Too risky without human-in-the-loop review |
| **Multi-user support** | Single-user tool for now |

### MVP Success Criteria

1. User can create a rant via chat and publish to Bluesky
2. User can configure radar sources and review a manually-triggered report
3. User can engage with signals through the report agent
4. Context persists across sessions and agents reflect it

---

## 2. Architecture Overview

### System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                           │
│   blah rant create | blah radar config | blah radar report  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                       Agent Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Rant Agent  │  │ Radar Config │  │ Radar Report │      │
│  │              │  │    Agent     │  │    Agent     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                 │
│                  ┌────────▼────────┐                        │
│                  │ Context Manager │ (Opus 4.5)             │
│                  │     Agent       │                        │
│                  └────────┬────────┘                        │
│                           │                                 │
│                    ┌──────▼──────┐                          │
│                    │ context.md  │  (shared memory)         │
│                    └─────────────┘                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     Service Layer                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  LLM Client │  │  Persistence │  │  Task Queue  │        │
│  │  (Claude)   │  │  (SQLite)    │  │  (SAQ+Redis) │        │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Adapter Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Bluesky  │  │ Mastodon │  │  Twitter │  │ Browser  │    │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Fallback │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Modular/layered architecture** - Clear separation between CLI, agents, services, and adapters
2. **Single-purpose agents** - Each agent owns a specific flow (rant, config, report, context management)
3. **API-first integration** - Official APIs where available, browser only as fallback
4. **Human-in-the-loop** - All engagements require user approval before sending

---

## 3. Agent Specifications

### 3.1 Rant Agent

**Purpose:** Help create and refine rants - content strategies for posting across platforms.

**Responsibilities:**
- Understand what the user wants to make noise about
- Refine angle and positioning through conversation
- Draft platform-specific pieces
- Propose schedule
- Finalize when ready

**System Prompt Injection:**
```
# Blah Rant Agent

You help create and refine rants - content for posting across platforms.

## User Context
{context.md contents}

## Current Rant
{rant state or "New rant - nothing yet"}

## Guidelines
- Match the user's voice (see context)
- Platform-appropriate content:
  - Twitter: punchy, thread-friendly
  - HN: technical, substantive
  - Reddit: subreddit-appropriate tone
  - Bluesky: conversational
- Ask clarifying questions before drafting
```

**Tools:**

| Tool | Signature | Description |
|------|-----------|-------------|
| `set_title` | `(text: str)` | Set rant title |
| `set_summary` | `(text: str)` | Set rant summary |
| `attach_resource` | `(path_or_url: str)` | Add image/video/doc/url |
| `create_piece` | `(platform: str, content: str, target: dict?, scheduled_at: datetime?)` | Create platform piece (target has platform-specific params) |
| `update_piece` | `(id: str, content: str)` | Edit existing piece |
| `suggest_context_update` | `(suggestion: str)` | Suggest update to Context Manager Agent |
| `finalize_rant` | `()` | Mark rant ready for publishing |

**Chat History:** Persisted in SQLite `chat_histories` table (key: `rant:{id}`)

---

### 3.2 Radar Config Agent

**Purpose:** Configure what sources to monitor and what interests to track.

**Responsibilities:**
- Understand what sources to monitor (accounts, subreddits, HN)
- Understand topics/people of interest
- Update configuration and context

**System Prompt Injection:**
```
# Blah Radar Config Agent

You help configure radar - what to monitor and what matters.

## User Context
{context.md contents}

## Current Sources
{list of configured sources}

## Guidelines
- Suggest relevant sources based on interests
- Keep config focused (too many sources = noise)
- Update context.md with interests for scoring
```

**Tools:**

| Tool | Signature | Description |
|------|-----------|-------------|
| `add_source` | `(platform: str, type: str, config: dict)` | Add a source (config is platform/type-specific) |
| `remove_source` | `(id: str)` | Remove a source |
| `list_sources` | `()` | Show current sources |
| `suggest_context_update` | `(suggestion: str)` | Suggest update to Context Manager Agent |
| `set_cadence` | `(interval: str)` | Set report generation interval |

**Chat History:** Persisted in SQLite `chat_histories` table (key: `radar_config`)

---

### 3.3 Radar Report Agent

**Purpose:** Review a specific report - walk through items, decide actions.

**Responsibilities:**
- Present items by relevance score
- Help user decide: engage, skip, or save
- Draft and send responses for engagements
- Track reviewed items
- Connect signals to existing rants

**System Prompt Injection:**
```
# Blah Radar Report Agent

You help review radar reports - signals, suggested follows, trends.

## User Context
{context.md contents}

## Report State
{report with items and statuses}

## Guidelines
- Start with highest relevance items
- Don't repeat reviewed items
- For engagements, match user's voice
- Suggest connections to rants when relevant
```

**Tools:**

| Tool | Signature | Description |
|------|-----------|-------------|
| `mark_reviewed` | `(item_id: str)` | Mark item as reviewed |
| `mark_skipped` | `(item_id: str)` | Skip item |
| `draft_engagement` | `(item_id: str, content: str)` | Draft a response |
| `send_engagement` | `(item_id: str)` | Send the drafted response |
| `follow` | `(platform: str, type: str, identifier: str)` | Follow user/subreddit/hashtag |
| `suggest_context_update` | `(suggestion: str)` | Suggest update to Context Manager Agent |
| `link_to_rant` | `(item_id: str, rant_id: str)` | Connect signal to rant |

**Chat History:** Persisted in SQLite `chat_histories` table (key: `report:{id}`)

---

### 3.4 Research Agent (Enhancement from Best Practices)

Per generator-critic patterns, the radar flow benefits from separating research from report presentation.

**Purpose:** Investigate signals, enrich context before report generation.

**Responsibilities:**
- Fetch full content for items flagged as relevant
- Research context (thread history, author background)
- Enrich items with investigation notes
- Score relevance based on context.md

**Implementation:** Part of the report generation pipeline, not user-facing.

**Model:** Configurable via `config.yaml`. Default strategy:
- `models.triage` - relevance scoring, filtering
- `models.research` - context enrichment
- `models.conversation` - user-facing agents (Rant, Config, Report)

Allows swapping providers (Anthropic, OpenAI, local) or tuning cost/quality tradeoffs.

---

## 4. Task Pipeline

### Deterministic vs Agent Tasks

| Task Type | Handler | When |
|-----------|---------|------|
| **Source polling** | Deterministic worker | Scheduled (cron or interval) |
| **Initial triage** | Small model (Haiku) | After polling completes |
| **Research/enrichment** | Research agent | For items passing triage |
| **Report generation** | Deterministic | After enrichment |
| **Report review** | Report Agent (Sonnet) | User-triggered |
| **Piece publishing** | Deterministic | User-triggered or scheduled |

### Task Queue Architecture

```
┌─────────────────┐
│   SAQ Worker    │◄────── Redis Queue
└────────┬────────┘
         │
         ├── poll_sources_task
         │      └── Platform adapters fetch new content
         │
         ├── triage_items_task
         │      └── Small model scores relevance
         │
         ├── research_item_task
         │      └── Research agent enriches item
         │
         ├── generate_report_task
         │      └── Compile items into report
         │
         └── publish_piece_task
                └── Platform adapter posts content
```

**MVP Simplification:** Start with synchronous execution via CLI, add SAQ workers post-MVP.

### Item Lifecycle

```
FeedItem
├── id: str
├── source_id: str
├── platform: str
├── external_id: str              # tweet id, post id, etc.
├── url: str
├── author: str
├── content: str
├── fetched_at: datetime
│
├── status: raw → triaged → researched → reported
│                    ↓
│                 discarded (below threshold)
│
│ # Set by triage
├── relevance_score: float?
├── triage_reason: str?
│
│ # Set by research
├── enrichment: {
│     full_thread: str?,
│     author_context: str?,
│     notes: str?
│   }
│
└── report_id: str?               # Set when added to report
```

### Pipeline Storage

All pipeline state in SQLite (`~/.blah/blah.db`):

```sql
-- FeedItems tracked by status column, not separate directories
SELECT * FROM feed_items WHERE status = 'raw';       -- Fresh from polling
SELECT * FROM feed_items WHERE status = 'triaged';   -- Awaiting research
SELECT * FROM feed_items WHERE status = 'researched';-- Awaiting report
SELECT * FROM feed_items WHERE status = 'discarded'; -- Below threshold
```

Indexed on `status`, `author`, `relevance_score` for fast queries.

### State Transitions

| Step | Query | Update | Action |
|------|-------|--------|--------|
| Poll | (external) | `INSERT status='raw'` | Fetch from adapters |
| Triage | `WHERE status='raw'` | `SET status='triaged'` or `'discarded'` | Score + filter |
| Research | `WHERE status='triaged'` | `SET status='researched'` | Enrich with context |
| Generate | `WHERE status='researched'` | `SET status='reported', report_id=?` | Compile report |

Each step is idempotent - items only move forward, can restart safely.

### Publishing Error Handling

```
Piece Status Flow:
                                    ┌──────────┐
approved → scheduled → publishing ──┤          ├──► published
                           │        │ success  │
                           │        └──────────┘
                           │
                           │        ┌──────────┐
                           └───────►│  failed  │◄─── retry limit hit
                                    └────┬─────┘
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                         auto-retry            manual override
                        (if retriable)      (mark as posted externally)
```

**On publish failure:**
1. Increment `retry_count`
2. Store `error` message
3. If retriable (rate limit, timeout) and under retry limit → re-queue
4. If permanent failure or retry limit hit → mark `failed`

**CLI commands for failed pieces:**
```bash
blah rant failures              # List all failed pieces
blah rant retry <piece_id>      # Retry a failed piece
blah rant mark-posted <piece_id> <url>  # Mark as manually posted
```

**Manual override flow:**
```
$ blah rant mark-posted 7 "https://twitter.com/you/status/123456"

Piece #7 marked as published.
  external_url: https://twitter.com/you/status/123456
  external_id: 123456 (extracted from URL)
```

---

## 5. Platform Adapters

### Adapter Interface

```python
class PlatformAdapter(ABC):
    @abstractmethod
    async def post(self, content: str, target: PostTarget, media: list[str] = None) -> Post:
        """Create a new post."""
        pass

    @abstractmethod
    async def reply(self, target_url: str, content: str) -> Post:
        """Reply to an existing post."""
        pass

    @abstractmethod
    async def read(self, url: str) -> dict:
        """Read a post/thread for context."""
        pass

    @abstractmethod
    async def follow(self, target: FollowTarget) -> bool:
        """Follow a user, subreddit, hashtag, etc."""
        pass

    @abstractmethod
    async def fetch_feed(self, source: Source) -> list[FeedItem]:
        """Fetch items from a configured source."""
        pass
```

### Platform-Specific Targets

```
PostTarget
├── platform: str
└── params: (platform-specific)
    ├── twitter: {}
    ├── bluesky: { langs?: list[str] }
    ├── mastodon: { visibility?: public|unlisted|private, cw?: str }
    └── reddit: { subreddit: str, flair?: str }

FollowTarget
├── platform: str
├── type: user | subreddit | hashtag | list
└── identifier: str
```

**What you can follow per platform:**

| Platform | user | subreddit | hashtag | list |
|----------|------|-----------|---------|------|
| Twitter | ✓ | - | - | ✓ |
| Bluesky | ✓ | - | - | - |
| Mastodon | ✓ | - | ✓ | - |
| Reddit | ✓ | ✓ | - | - |

### MVP Adapters

| Platform | Method | SDK | Priority |
|----------|--------|-----|----------|
| **Bluesky** | API | `atproto` | High (start here) |
| **Mastodon** | API | `Mastodon.py` | High |
| **Twitter** | API | `tweepy` | High |

### Integration Strategy

1. **API-first:** Use official APIs for all supported operations
2. **Browser fallback:** Reserve for platforms without write APIs (HN, LinkedIn)
3. **Rate awareness:** Track rate limits per platform, queue appropriately
4. **Credential management:** Environment variables for secrets, config file for settings

### Configuration

```yaml
models:
  # Tiered model strategy - cheap for triage, frontier for conversation
  triage:
    provider: anthropic
    model: claude-3-haiku-20240307
  research:
    provider: anthropic
    model: claude-3-haiku-20240307
  conversation:
    provider: anthropic
    model: claude-sonnet-4-20250514

  # Override per-agent if needed
  # rant_agent:
  #   provider: anthropic
  #   model: claude-opus-4-20250514
  # report_agent:
  #   provider: openai
  #   model: gpt-4o

providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  openai:
    api_key: ${OPENAI_API_KEY}
  # local:
  #   base_url: http://localhost:11434/v1

platforms:
  bluesky:
    enabled: true
    method: api
    handle: ${BLAH_BLUESKY_HANDLE}
    app_password: ${BLAH_BLUESKY_PASSWORD}

  mastodon:
    enabled: true
    method: api
    instance: ${BLAH_MASTODON_INSTANCE}
    access_token: ${BLAH_MASTODON_TOKEN}

  twitter:
    enabled: true
    method: api
    consumer_key: ${BLAH_TWITTER_CONSUMER_KEY}
    consumer_secret: ${BLAH_TWITTER_CONSUMER_SECRET}
    access_token: ${BLAH_TWITTER_ACCESS_TOKEN}
    access_token_secret: ${BLAH_TWITTER_ACCESS_SECRET}
```

---

## 6. Context Management

### context.md - Shared Memory

All agents read and can update `context.md`. This is the shared memory that persists user preferences, voice, and interests across sessions.

**Structure:**
```markdown
# Context

## Voice
Technical, direct, no buzzwords. Slightly contrarian.

## Topics
- AI agent memory systems
- Voice AI pipelines
- Cognitive architectures

## People
- @karpathy - agents/memory
- @simonw - LLM tooling

## Platforms
- Twitter: yes
- HN: yes
- Reddit: yes
- LinkedIn: never

## Notes
- Don't post before 9am
- OpenClaw is just MEMORY.md, we have real architecture
```

### Context Constraints

| Constraint | Value | Rationale |
|------------|-------|-----------|
| **Max size** | Configurable (`context.max_tokens`) | Default 2000 |
| **Update method** | Context Manager Agent | Intelligent, not mechanical |
| **Sections** | Flexible | Agent decides structure |

### Context Manager Agent

Instead of a code-based merge protocol, a dedicated agent handles all context updates.

**Model:** Locked to Opus 4.5 (or best available) - context is too important for cheaper models.

**Flow:**
```
Rant Agent                     Context Manager Agent
     │                                   │
     │  suggest_context_update(          │
     │    "User prefers technical        │
     │     tone, no emojis"              │
     │  )                                │
     │ ─────────────────────────────────►│
     │                                   │
     │                         ┌─────────┴─────────┐
     │                         │ Reads context.md  │
     │                         │ Considers:        │
     │                         │  - Is this new?   │
     │                         │  - Contradicts?   │
     │                         │  - Where to put?  │
     │                         │  - Need to trim?  │
     │                         └─────────┬─────────┘
     │                                   │
     │                         Writes updated context.md
     │◄──────────────────────────────────│
     │  { success: true,                 │
     │    summary: "Added to Voice" }    │
```

**Why an agent, not code:**
- Resolves contradictions ("prefers short posts" vs "likes detailed threads")
- Summarizes when trimming, doesn't just truncate
- Restructures sections as context evolves
- Rejects nonsense updates

**Config:**
```yaml
context:
  path: context.md
  max_tokens: 2000
  model:
    provider: anthropic
    model: claude-opus-4-20250514  # Locked to best model
```

**Tool signature (used by all other agents):**
```
suggest_context_update(suggestion: str) → { success: bool, summary: str }
```

Replaces direct `update_context()` - agents suggest, Context Manager decides.

---

## 7. Data Model

### Core Entities

```
Rant
├── id: str
├── title: str
├── summary: str
├── resources: list[Resource]
├── pieces: list[Piece]
├── status: draft | active | complete
└── created_at: datetime

Piece
├── id: str
├── rant_id: str
├── platform: bluesky | mastodon | twitter | ...
├── content: str
├── target: PostTarget?              # Platform-specific (subreddit, visibility, etc.)
├── resources: list[Resource]
├── scheduled_at: datetime?
├── status: draft | approved | scheduled | publishing | published | failed
│
│ # Set after publish attempt
├── external_id: str?                # Tweet ID, post ID, etc.
├── external_url: str?               # Link to the published post
├── published_at: datetime?
│
│ # Set on failure
├── error: str?                      # Last error message
├── retry_count: int                 # Number of attempts
└── manual_override: {               # If manually posted outside blah
      external_id: str,
      external_url: str,
      posted_at: datetime
    }?

Resource
├── id: str
├── type: image | video | doc | url
└── location: str

Source
├── id: str
├── platform: twitter | bluesky | mastodon | reddit | hn
├── type: (platform-specific, see below)
├── config: (platform-specific fields)
├── state: (polling state - cursors, last_seen, etc.)
└── enabled: bool

Source Types by Platform:
┌──────────┬────────────┬─────────────────────┬──────────────────────────┐
│ Platform │ Type       │ Config Fields       │ State Fields             │
├──────────┼────────────┼─────────────────────┼──────────────────────────┤
│ twitter  │ account    │ handle              │ last_tweet_id            │
│          │ list       │ list_id             │ last_tweet_id            │
│          │ search     │ query               │ last_tweet_id            │
├──────────┼────────────┼─────────────────────┼──────────────────────────┤
│ bluesky  │ account    │ did, handle         │ cursor                   │
│          │ feed       │ feed_uri            │ cursor                   │
├──────────┼────────────┼─────────────────────┼──────────────────────────┤
│ mastodon │ account    │ instance, account_id│ last_status_id           │
│          │ hashtag    │ instance, tag       │ last_status_id           │
├──────────┼────────────┼─────────────────────┼──────────────────────────┤
│ reddit   │ subreddit  │ subreddit           │ last_post_id             │
│          │ user       │ username            │ last_post_id             │
├──────────┼────────────┼─────────────────────┼──────────────────────────┤
│ hn       │ frontpage  │ -                   │ last_item_id             │
│          │ new        │ -                   │ last_item_id             │
│          │ user       │ username            │ last_item_id             │
└──────────┴────────────┴─────────────────────┴──────────────────────────┘

Each source type maps to a fetch action in the platform adapter.

FeedItem
├── id: str
├── source_id: str
├── platform: str
├── external_id: str              # Tweet ID, post ID, etc.
├── url: str
├── author: str
├── content: str
├── fetched_at: datetime
├── status: raw | triaged | researched | reported | discarded
│
│ # Set by triage
├── relevance_score: float?
├── triage_reason: str?
│
│ # Set by research
├── enrichment: {
│     full_thread: str?,
│     author_context: str?,
│     notes: str?
│   }?
│
└── report_id: str?               # Set when added to report

Report
├── id: str
├── generated_at: datetime
├── status: pending | in_review | complete
├── items: list[ReportItem]
└── sources_polled: list[str]

ReportItem
├── id: str
├── report_id: str
├── type: signal | suggested_follow | trending_topic
├── data: {url, author, snippet, reason}
├── relevance_score: float
├── status: new | reviewed | actioned | skipped
└── outcome: str?
```

### Storage Location

Default: `~/.blah/` (override with `BLAH_HOME` env var)

```
~/.blah/
├── config.yaml              # Platforms, credentials, settings
├── context.md               # Shared context (configurable max tokens)
├── blah.db                  # SQLite database (all entities)
└── resources/               # Uploaded files (binary, not in DB)
```

### SQLite Schema

```sql
-- Rant flow
CREATE TABLE rants (
    id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    status TEXT CHECK(status IN ('draft', 'active', 'complete')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pieces (
    id TEXT PRIMARY KEY,
    rant_id TEXT REFERENCES rants(id),
    platform TEXT NOT NULL,
    content TEXT NOT NULL,
    target JSON,                    -- Platform-specific (subreddit, visibility)
    scheduled_at TIMESTAMP,
    status TEXT CHECK(status IN ('draft', 'approved', 'scheduled', 'publishing', 'published', 'failed')),
    external_id TEXT,               -- Tweet ID, post ID after publish
    external_url TEXT,
    published_at TIMESTAMP,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    manual_override JSON
);

CREATE TABLE resources (
    id TEXT PRIMARY KEY,
    type TEXT CHECK(type IN ('image', 'video', 'doc', 'url')),
    location TEXT NOT NULL
);

-- Radar flow
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    type TEXT NOT NULL,
    config JSON NOT NULL,           -- Platform-specific fields
    state JSON DEFAULT '{}',        -- Cursors, last_seen
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE feed_items (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES sources(id),
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    author TEXT,
    content TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT CHECK(status IN ('raw', 'triaged', 'researched', 'reported', 'discarded')),
    relevance_score REAL,
    triage_reason TEXT,
    enrichment JSON,
    report_id TEXT REFERENCES reports(id)
);
CREATE INDEX idx_feed_items_status ON feed_items(status);
CREATE INDEX idx_feed_items_author ON feed_items(author);
CREATE INDEX idx_feed_items_score ON feed_items(relevance_score);

CREATE TABLE reports (
    id TEXT PRIMARY KEY,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT CHECK(status IN ('pending', 'in_review', 'complete')),
    sources_polled JSON
);

CREATE TABLE report_items (
    id TEXT PRIMARY KEY,
    report_id TEXT REFERENCES reports(id),
    type TEXT CHECK(type IN ('signal', 'suggested_follow', 'trending_topic')),
    data JSON NOT NULL,
    relevance_score REAL,
    status TEXT CHECK(status IN ('new', 'reviewed', 'actioned', 'skipped')),
    outcome TEXT
);

-- Chat histories (stored as JSON arrays)
CREATE TABLE chat_histories (
    id TEXT PRIMARY KEY,            -- e.g., "rant:4", "report:14", "radar_config"
    messages JSON NOT NULL DEFAULT '[]'
);
```

### Why SQLite

- **FeedItems scale**: 500+/day polling → 15K/month. JSON search is O(n), SQLite is indexed.
- **Single file**: Still easy to backup, no server needed.
- **Built-in**: Python `sqlite3`, no dependencies.
- **Queryable**: "Items from @karpathy with score > 0.7" is instant.

### MVP Simplification

- **No ORM:** Raw SQL with simple helper functions
- **No migrations framework:** Schema changes via versioned SQL scripts
- **No multi-tenancy:** Single user, single database

---

## 8. CLI Interface

### Commands

```bash
# Rants
blah rant create              # Start new rant (chat)
blah rant list                # List all rants
blah rant chat <id>           # Resume rant conversation
blah rant show <id>           # Show rant details
blah rant publish <id>        # Publish approved pieces
blah rant delete <id>         # Delete a rant
blah rant failures            # List failed pieces
blah rant retry <piece_id>    # Retry a failed piece
blah rant mark-posted <piece_id> <url>  # Mark as manually posted

# Radar
blah radar config             # Configure sources via chat (agent suggests sources)
blah radar pull               # Manually trigger source polling
blah radar report             # Review oldest pending report (chat)
blah radar report <id>        # Review specific report
blah radar status             # Show radar configuration

# Context
blah context show             # Display context.md
blah context edit             # Open in $EDITOR

# Config
blah config show              # Show current configuration
blah config edit              # Open config.yaml in $EDITOR
blah config models            # Configure models per agent/task (interactive)
blah config credentials       # Set up platform API keys (interactive)
blah config sources           # Manage radar sources (add/remove/list)

# System
blah init                     # Initialize ~/.blah directory
blah status                   # Show system status
```

### CLI Framework

- **Click** for command structure
- **Rich** for terminal formatting
- **Prompt Toolkit** for chat interface

---

## 9. Best Practices Alignment

### Industry Pattern Mapping

| Best Practice | Source | Blah Implementation |
|--------------|--------|---------------------|
| **Modular architecture** | Exabeam, Databricks | Agent layer separate from adapters, clear service boundaries |
| **Single-purpose agents** | Google Multi-Agent | Four specialized agents (Rant, Config, Report, Context Manager) |
| **Generator-critic pattern** | Databricks | Research agent scores/enriches, Report agent presents/critiques |
| **Shared context management** | JetBrains, Mem0 | context.md managed by Context Manager Agent (Opus 4.5) |
| **Tool typing with schemas** | All sources | Typed tool signatures, clear input/output contracts |
| **API-first integration** | OneReach | Official APIs preferred, browser only as fallback |
| **Heterogeneous model strategy** | Medium (Rana) | Configurable tiers: cheap for triage, frontier for conversation |
| **Context trimming** | JetBrains | Configurable max tokens, Context Manager summarizes when trimming |
| **Clear agent handoffs** | Google | Each agent owns specific flow, explicit transitions |
| **Human-in-the-loop** | HBR | All engagements require approval before sending |

### Key Enhancements from Research

1. **Research Agent Separation**
   - Per generator-critic patterns, radar separates collection from analysis
   - Collector (deterministic polling) → Research Agent (enrichment) → Report Agent (user interaction)

2. **Tiered Model Usage**
   - Configurable per task type (triage, research, conversation)
   - Allows cost/quality tuning and provider flexibility

3. **Context Manager Agent**
   - Dedicated agent (Opus 4.5) handles all context.md updates
   - Resolves contradictions, summarizes when trimming, rejects nonsense

4. **Deterministic vs Agent Tasks**
   - Polling, publishing, report generation: deterministic workers
   - Conversation, decision-making, synthesis: agent loops

---

## 10. Implementation Roadmap

### Phase 1: Foundation
1. Project structure (Python, Click, pyproject.toml)
2. CLI skeleton with all commands stubbed
3. Persistence layer (SQLite + helper functions)
4. Config loading (YAML + env vars)

### Phase 2: Rant Flow
1. Rant Agent implementation
2. Tool implementations (set_title, create_piece, etc.)
3. Chat loop with history persistence
4. Bluesky adapter (post only)

### Phase 3: Radar Flow
1. Source configuration persistence
2. Radar Config Agent
3. Manual polling (blah radar pull)
4. Basic report generation
5. Report Agent implementation

### Phase 4: Integration
1. Mastodon adapter
2. Twitter adapter
3. Context Manager Agent implementation
4. Full end-to-end testing

### Phase 5: Polish
1. Error handling and recovery
2. Rate limit awareness
3. CLI UX improvements
4. Documentation

---

## Appendix A: Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.12+ | Ecosystem, SDK support |
| **CLI** | Click + Rich | Industry standard, good UX |
| **Chat UI** | Prompt Toolkit | Full readline, history |
| **LLM** | Configurable (Claude default) | Provider-agnostic client, tool use support |
| **Persistence** | SQLite | Single file, indexed queries, built into Python |
| **Task Queue** | SAQ + Redis | Lightweight, Python-native |
| **HTTP** | httpx | Async support |

---

## Appendix B: References

- [Agentic AI Architecture Guide](https://www.exabeam.com/explainers/agentic-ai/agentic-ai-architecture-types-components-best-practices/)
- [Enterprise AI Agent Best Practices 2026](https://onereach.ai/blog/best-practices-for-ai-agent-implementations/)
- [HBR: Designing Successful Agentic AI](https://hbr.org/2025/10/designing-a-successful-agentic-ai-system)
- [Agentic AI Design Patterns 2026](https://medium.com/@dewasheesh.rana/agentic-ai-design-patterns-2026-ed-e3a5125162c5)
- [Databricks Agent System Design Patterns](https://docs.databricks.com/aws/en/generative-ai/guide/agent-system-design-patterns)
- [Google Multi-Agent Patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [AI Agent Memory Best Practices](https://mem0.ai/blog/memory-in-agents-what-why-and-how)
- [JetBrains Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
