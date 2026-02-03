# Blah

Social engagement agent. Makes noise so you don't have to.

## What Is This

Blah is a CLI tool with two main flows:

1. **Rant** - Create content, distribute across platforms (Bluesky, Mastodon, Twitter)
2. **Radar** - Monitor feeds, surface relevant signals, engage when appropriate

All interactions are chat-based with persistent agents. You talk to agents, they do the work.

## Status

**Design phase.** See [`docs/final-design.md`](docs/final-design.md) for the complete MVP specification.

## Key Concepts

- **Rant**: A topic you want to make noise about. Contains pieces for each platform.
- **Piece**: Platform-specific content (a tweet, Bluesky post, etc.)
- **Radar**: Background monitoring of feeds for relevant signals.
- **Report**: Periodic digest of signals, suggested follows, trending topics.
- **context.md**: Shared memory across all agents. Voice, interests, notes.

## Architecture

Four agents, each with a specific purpose:

| Agent | Purpose |
|-------|---------|
| **Rant Agent** | Create and refine content for posting |
| **Radar Config Agent** | Configure what sources to monitor |
| **Radar Report Agent** | Review reports and decide on engagements |
| **Context Manager Agent** | Manage shared context (locked to best model) |

## CLI (Planned)

```bash
# Rants
blah rant create              # Start new rant (chat)
blah rant list                # List all rants
blah rant chat <id>           # Resume rant conversation
blah rant publish <id>        # Publish approved pieces

# Radar
blah radar config             # Configure sources (chat)
blah radar pull               # Trigger source polling
blah radar report             # Review latest report (chat)

# Config
blah config models            # Configure LLM providers/models
blah config credentials       # Set up platform API keys
```

## Tech Stack

- Python 3.12+
- Click + Rich + Prompt Toolkit (CLI)
- SQLite (persistence)
- Configurable LLM (Claude default)

## Documentation

- [`docs/final-design.md`](docs/final-design.md) - Complete MVP design
- [`docs/use-cases.md`](docs/use-cases.md) - User flows
- [`docs/agent-design.md`](docs/agent-design.md) - Agent specifications
- [`docs/domain-model.md`](docs/domain-model.md) - Data structures
- [`docs/integrations.md`](docs/integrations.md) - Platform integration strategy

## License

MIT
