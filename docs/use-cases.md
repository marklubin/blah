# Blah - Use Cases

## Overview

Blah is a social engagement agent that handles content creation and distribution so you don't have to. Two main flows:

1. **Rant** - Create content, distribute across platforms
2. **Radar** - Monitor feeds, surface relevant signals, engage

The goal: minimal attention from you, maximum presence online.

---

## Rant Flow

### UC-1: Create a Rant

**Entry:** `blah rant create`

**Flow:**
1. Enter chat loop with rant agent
2. Discuss what you want to make noise about
3. Agent helps refine the angle/positioning
4. Attach resources (images, videos, links) as needed
5. Agent drafts platform-specific pieces (twitter, hn, reddit, etc.)
6. Agent proposes schedule
7. Finalize when ready

**Output:** Rant entity with pieces ready to publish

**Example:**
```
$ blah rant create

[assistant] What do you want to make noise about?

> AI memory systems. everyone's hyping OpenClaw but it's
> literally just markdown files. I built actual infrastructure.

[assistant] Spicy. What's the core differentiator?

> semantic graphs, provenance tracking, hierarchical summarization
> /attach architecture.png

[assistant] So the angle is "here's what real memory looks like"?

> yeah but educational, not attack

[assistant] Got it. Core insight: "Most AI memory is just text
accumulation. Real memory needs structure and hierarchy."

Ready to create pieces for twitter, hn, reddit?

> yes

[assistant] Created rant #4. Generating pieces...
```

### UC-2: Resume/Refine a Rant

**Entry:** `blah rant chat <id>`

**Flow:**
1. Agent loads rant state + chat history
2. Resume conversation where you left off
3. Refine pieces, adjust schedule, add resources

### UC-3: Run a Rant

**Entry:** `blah rant run <id>`

**Flow:**
1. Execute the schedule
2. Publish pieces at scheduled times

---

## Radar Flow

### UC-4: Configure Radar

**Entry:** `blah radar config`

**Flow:**
1. Enter chat loop with config agent
2. Discuss what sources to monitor (twitter lists, subreddits, HN, accounts)
3. Discuss topics/interests to track
4. Agent updates configuration

**Example:**
```
$ blah radar config

[assistant] What do you want to keep tabs on?

> AI agent stuff. the LocalLLaMA subreddit, HN front page,
> and a few people - karpathy, simonw

[assistant] Got it. Adding:
- r/LocalLLaMA
- HN front page
- @karpathy
- @simonw

Any topics to watch for specifically?

> AI memory, voice AI, agent architectures

[assistant] Added. I'll flag anything relevant to those.
```

### UC-5: Review Radar Report

**Entry:** `blah radar report`

**Flow:**
1. Agent loads oldest report with unreviewed items
2. Walk through items one by one:
   - Signals (engagement opportunities)
   - Suggested follows
   - Trending topics
3. For each: engage, skip, or save for later
4. Agent tracks decisions, doesn't repeat reviewed items

**Example:**
```
$ blah radar report

[assistant] Report from Feb 2, 3 items pending.

First up:

SIGNAL: @karpathy thread on agent memory
"The problem with most AI agents is memory..."
Relevance: high (matches your interests + rants)

Want to engage, skip, or save?

> let's engage

[assistant] Draft:
"This. The missing piece is treating memory as structure,
not log file..."

> good, send it

[assistant] Sent. Next:

SUGGESTED FOLLOW: @simonw
Reason: LLM tooling, overlaps with your topics

Follow?

> yes

[assistant] Done. Report complete.
```

---

## Interaction Modes

| Mode | You Do | Blah Does |
|------|--------|-----------|
| **Rant create** | Chat to refine content | Drafts pieces, schedules |
| **Rant run** | Trigger or let schedule run | Publishes across platforms |
| **Radar config** | Chat to set sources | Monitors in background |
| **Radar report** | Review when convenient | Surfaces what matters |

---

## What Triggers Your Attention

- `blah radar report` when you feel like checking in
- Everything else runs in background

No notifications, no pressure. You check when you want.
