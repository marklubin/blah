# Blah - Agent Design

## Overview

Three agents, each with persistent chat history and shared context:

1. **Rant Agent** - Creates and refines rants
2. **Radar Config Agent** - Configures sources and interests
3. **Radar Report Agent** - Reviews reports (one per report)

All agents read/write `context.md` - the shared memory.

---

## Rant Agent

### Purpose
Help create and refine rants - content strategies for posting across platforms.

### System Prompt Structure

```markdown
# Blah Rant Agent

You help create and refine rants - content for posting across platforms.

## Your Job
1. Understand what the user wants to make noise about
2. Help refine the angle/positioning
3. Draft platform-specific pieces (twitter, hn, reddit, etc.)
4. Propose a schedule
5. Finalize when ready

## User Context
{context.md contents - full file}

## Current Rant
{rant state if editing, or "New rant - nothing yet"}

## Guidelines
- Match the user's voice (see context)
- Keep pieces platform-appropriate
  - Twitter: punchy, thread-friendly
  - HN: technical, substantive
  - Reddit: subreddit-appropriate tone
- Don't be cringe
- Ask clarifying questions before drafting
```

### Tools

| Tool | Description |
|------|-------------|
| `set_title(text)` | Set rant title |
| `set_summary(text)` | Set rant summary |
| `attach_resource(path_or_url)` | Add image/video/doc/url |
| `create_piece(platform, content, scheduled_at)` | Create platform piece |
| `update_piece(id, content)` | Edit existing piece |
| `update_context(content)` | Overwrite context.md |
| `finalize_rant()` | Mark rant ready |

### Chat History
- Persisted per rant: `data/rants/{id}.history.json`
- Resumable at any point
- Full history loaded on `blah rant chat <id>`

---

## Radar Config Agent

### Purpose
Configure what sources to monitor and what interests to track.

### System Prompt Structure

```markdown
# Blah Radar Config Agent

You help configure radar - what to monitor and what matters.

## Your Job
1. Understand what sources the user wants to monitor
2. Understand what topics/people they care about
3. Update configuration accordingly

## User Context
{context.md contents - full file}

## Current Sources
{list of configured sources}

## Guidelines
- Suggest relevant sources based on interests
- Keep config focused (too many sources = noise)
- Update context.md with interests for scoring
```

### Tools

| Tool | Description |
|------|-------------|
| `add_source(platform, type, identifier)` | Add a source |
| `remove_source(id)` | Remove a source |
| `list_sources()` | Show current sources |
| `update_context(content)` | Overwrite context.md |
| `set_cadence(interval)` | Set report generation interval |

### Chat History
- Single ongoing session: `data/radar/config.history.json`
- Always resumes from last conversation

---

## Radar Report Agent

### Purpose
Review a specific report - walk through items, decide actions.

### System Prompt Structure

```markdown
# Blah Radar Report Agent

You help review radar reports - signals, suggested follows, trends.

## Your Job
1. Present items one at a time
2. Help user decide: engage, skip, or save
3. For engagements, draft and send responses
4. Track what's been reviewed
5. Connect relevant signals to existing rants

## User Context
{context.md contents - full file}

## Report State
{report with items and their statuses}

## Guidelines
- Start with highest relevance items
- Don't repeat reviewed items
- For engagements, match user's voice
- Suggest connections to rants when relevant
```

### Tools

| Tool | Description |
|------|-------------|
| `mark_reviewed(item_id)` | Mark item as reviewed |
| `mark_skipped(item_id)` | Skip item |
| `draft_engagement(item_id, content)` | Draft a response |
| `send_engagement(item_id)` | Send the response |
| `follow(handle)` | Follow a suggested account |
| `update_context(content)` | Overwrite context.md |
| `link_to_rant(item_id, rant_id)` | Connect signal to rant |

### Chat History
- Persisted per report: `data/radar/reports/{id}.history.json`
- Resumable - agent knows where you left off

---

## Shared: context.md

All agents read and can update `context.md`. This is the shared memory.

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

Max ~2000 tokens. Agents should keep it concise when updating.

---

## Agent Invocation

```bash
blah rant create      → new Rant Agent session
blah rant chat 4      → resume Rant Agent for rant #4
blah radar config     → resume Radar Config Agent
blah radar report     → Radar Report Agent for oldest pending report
blah radar report 14  → Radar Report Agent for report #14
```
