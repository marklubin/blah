# Blah - Domain Model

## Entities

### Rant

The core content unit - a topic you want to make noise about.

```
Rant
├── id
├── title
├── summary
├── resources[]
├── pieces[]
├── status (draft/active/complete)
└── chat_session_id
```

### Piece

Platform-specific content derived from a rant.

```
Piece
├── id
├── rant_id
├── platform (twitter/hn/reddit/linkedin)
├── content
├── resources[]
├── scheduled_at
└── status (draft/approved/scheduled/published)
```

### Resource

Attachable media - images, videos, docs, URLs.

```
Resource
├── id
├── type (image/video/doc/url)
└── location (file path or URL)
```

### Source

A feed to monitor for radar.

```
Source
├── id
├── platform (twitter/hn/reddit)
├── type (account/list/topic/subreddit/frontpage)
├── identifier (@karpathy, "ai-builders", "LocalLLaMA")
└── enabled
```

### Report

Generated periodically from monitoring sources.

```
Report
├── id
├── generated_at
├── status (pending/in_review/complete)
├── items[]
└── chat_session_id
```

### ReportItem

An item within a report - signal, follow suggestion, or trend.

```
ReportItem
├── id
├── report_id
├── type (signal/suggested_follow/trending_topic)
├── data {url, author, snippet, reason}
├── relevance_score
├── status (new/reviewed/actioned/skipped)
└── outcome (what we decided)
```

### ChatSession

Persistent conversation with an agent.

```
ChatSession
├── id
├── entity_type (rant/radar_config/report)
├── entity_id
└── messages[]
```

---

## Relationships

```
Rant 1:N Piece
Rant 1:N Resource (attached)
Piece 1:N Resource (used)

Source 1:N Report (generates)
Report 1:N ReportItem

ChatSession 1:1 Rant
ChatSession 1:1 Report
ChatSession 1:1 RadarConfig (singleton)
```

---

## File Structure

```
blah/
├── config.yaml              # platforms, credentials, cadence
├── context.md               # shared context (~2000 tokens)
├── data/
│   ├── rants/
│   │   ├── 1.json           # rant entity
│   │   ├── 1.history.json   # chat history
│   │   ├── 2.json
│   │   └── 2.history.json
│   ├── radar/
│   │   ├── sources.json     # configured sources
│   │   ├── config.history.json  # config agent history
│   │   └── reports/
│   │       ├── 1.json
│   │       ├── 1.history.json
│   │       ├── 2.json
│   │       └── 2.history.json
│   └── resources/           # uploaded files
└── journal/                 # session journals
```

---

## Status Flows

### Rant Status

```
draft → active → complete
        ↓
      (pieces publish on schedule)
```

### Piece Status

```
draft → approved → scheduled → published
```

### Report Status

```
pending → in_review → complete
          (items reviewed one by one)
```

### ReportItem Status

```
new → reviewed → actioned
         ↓
       skipped
```

---

## Context File

`context.md` is the shared brain. All agents read it, all can update it.

```markdown
# Context

## Voice
Technical, direct, no buzzwords.

## Topics
- AI agent memory systems
- Voice AI pipelines

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
```

Fixed length (~2000 tokens max). Agents maintain conciseness.
