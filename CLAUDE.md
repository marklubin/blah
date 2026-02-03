# Blah

Social engagement agent. Makes noise so you don't have to.

## What Is This

Blah is a CLI tool with two main flows:

1. **Rant** - Create content, distribute across platforms (twitter, hn, reddit)
2. **Radar** - Monitor feeds, surface relevant signals, engage when appropriate

All interactions are chat-based with persistent agents. You talk to agents, they do the work.

## Key Concepts

- **Rant**: A topic you want to make noise about. Contains pieces for each platform.
- **Piece**: Platform-specific content (a tweet thread, HN post, reddit comment).
- **Radar**: Background monitoring of feeds for relevant signals.
- **Report**: Periodic digest of signals, suggested follows, trending topics.
- **context.md**: Shared memory across all agents. Voice, interests, notes.

## CLI

```bash
# Rants
blah rant create          # chat to create new rant
blah rant list            # list rants
blah rant chat <id>       # resume/refine a rant
blah rant run <id>        # execute the schedule

# Radar
blah radar config         # chat to configure sources
blah radar report         # chat to review latest report
blah radar report <id>    # review specific report
```

## Architecture

Three agents:
- **Rant Agent**: Creates/refines rants, drafts pieces
- **Radar Config Agent**: Configures what to monitor
- **Radar Report Agent**: Reviews reports, handles engagement

All agents share `context.md` and can update it.

See `docs/` for details:
- `docs/use-cases.md` - User flows
- `docs/agent-design.md` - Agent specs
- `docs/domain-model.md` - Data structures

## Journaling Protocol

After each work session on this project, Claude writes a journal entry.

### Journal Entry Format

File: `journal/YYYY-MM-DD-NN.md` (NN = sequence number for the day)

```markdown
# Session Journal - YYYY-MM-DD-NN

## Summary
One paragraph: what was accomplished this session.

## Decisions Made
- Bullet list of key decisions and rationale

## Changes
- Files created/modified
- Features added
- Bugs fixed

## Open Questions
- Unresolved issues
- Things to think about

## Next Steps
- What to pick up next session
```

### When to Journal

- End of every work session
- Before switching to unrelated work
- When making significant decisions

### Journal Location

```
blah/
└── journal/
    ├── 2026-02-02-01.md
    ├── 2026-02-02-02.md
    └── ...
```

## Tech Stack (TBD)

- Python
- Click (CLI)
- Anthropic Claude API (agents)
- SQLite or JSON files (persistence)

## Status

Design phase. Domain model and agent designs complete. Implementation not started.
