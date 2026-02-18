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

## Tech Stack

- Python 3.13 (via uv)
- Click (CLI)
- Anthropic Claude API (agents)
- SQLite (persistence via SQLAlchemy + Alembic)
- atproto (Bluesky), requests-oauthlib (Twitter), PRAW-style (Reddit), httpx (Discord via MCP router), Telethon (Telegram)

## Deployment — Salinas

Blah is deployed on the `salinas` server (reachable via `ssh salinas` / Tailscale).

### Server Info

- Pop!_OS 24.04 LTS, x86_64, 16 CPUs, 123GB RAM
- Python 3.13 via uv (`~/.local/bin/uv`)
- Tailscale connected — can reach oxnard (100.96.58.51) where the primary MCP router runs

### Installed Components

| Component | Location | Notes |
|-----------|----------|-------|
| **blah** | `~/blah` | Cloned from GitHub, installed via `uv sync` |
| **MCP router** | `~/mcp-infrastructure` | Cloned from `mcp-email-server` repo |
| **Playwright chromium** | `~/.cache/ms-playwright/` | For browser automation |
| **uv** | `~/.local/bin/uv` | Python package manager |

### Config Files

| File | Purpose |
|------|---------|
| `~/.blah/config.yaml` | Blah platform credentials and model config |
| `~/.blah/context.md` | Shared agent memory (voice, interests) |
| `~/.blah/blah.db` | SQLite database |
| `~/mcp-infrastructure/.env` | MCP router env vars (DISCORD_TOKEN, ROUTER_PORT, etc.) |

### Systemd User Services

| Service | Description |
|---------|-------------|
| `blah-vnc.service` | TigerVNC on `:1` (port 5901), 1920x1080, runs Xfce4 |
| `mcp-router@mark.service` | MCP router on `0.0.0.0:8080`, `DISPLAY=:1` for browser automation |

Lingering is enabled — services survive logout.

```bash
# Manage services
ssh salinas "systemctl --user status blah-vnc mcp-router@mark"
ssh salinas "systemctl --user restart mcp-router@mark"
ssh salinas "journalctl --user-unit mcp-router@mark -f"
```

### VNC Browser Instance

Display `:1` on port 5901 runs a dedicated Xfce4 desktop for browser auth sessions (LinkedIn, Discord token extraction, etc.). Connect with any VNC client to `salinas:5901`.

- xstartup: `~/.vnc/xstartup` (launches Xfce4)
- The MCP router's browser backend runs on this display (`DISPLAY=:1`)

### Platform Auth Reference

| Platform | Auth Method | Config Location |
|----------|------------|-----------------|
| **Bluesky** | Handle + app password | `~/.blah/config.yaml` → `platforms.bluesky` |
| **Twitter** | OAuth 2.0 or `blah config auth twitter` | `~/.blah/config.yaml` → `platforms.twitter` |
| **Reddit** | OAuth client_id/secret + username/password | `~/.blah/config.yaml` → `platforms.reddit` |
| **Discord** | User token via MCP router | `~/mcp-infrastructure/.env` → `DISCORD_TOKEN` |
| **HackerNews** | No auth (public API) | `~/.blah/config.yaml` → `platforms.hackernews` (just `enabled: true`) |
| **Telegram** | API ID + hash + session string | `~/.blah/config.yaml` → `platforms.telegram` |
| **LinkedIn** | Browser session via VNC | Login in VNC browser, router scrapes via CDP |

### Running Blah on Salinas

```bash
ssh salinas
cd ~/blah
~/.local/bin/uv run blah radar health    # check platform status
~/.local/bin/uv run blah radar config    # configure sources
~/.local/bin/uv run blah radar pull      # pull from feeds
~/.local/bin/uv run blah radar report    # review latest report
```

### Remaining Setup

- `ANTHROPIC_API_KEY` must be set in shell profile and/or systemd service env
- Platform credentials need to be filled in (see Platform Auth Reference above)
- VNC packages need sudo install: `sudo apt install -y tigervnc-standalone-server tigervnc-common dbus-x11 xfce4 xfce4-terminal`
- VNC password needs to be set: `vncpasswd`
