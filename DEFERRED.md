# Deferred Features

Features explicitly out of scope for MVP and why.

## Platform Adapters
- **Mastodon adapter** — Add after Twitter is stable
- **Reddit / Threads / HN / LinkedIn adapters** — Different content styles, API approval overhead
- **Browser fallback adapter** — Only needed for platforms without write APIs

## Rant Agent Tools
- **Social platform search** — Search Bluesky/Twitter for relevant posts, trends, hashtags to inform content

## Platform-Specific Voice/Style
- **Per-platform voice config** — Add platform-specific tone/style notes to config (e.g., Bluesky more casual, Twitter more punchy, LinkedIn more professional)
- **Inject into Rant Agent prompt** — When creating pieces, inject relevant platform voice notes so content is tailored
- **Could live in**: context.md sections, config.yaml per-platform block, or separate `platforms/bluesky.md` files

## Chat UI
- **prompt_toolkit chat UI** — Upgrade from `input()` later for readline, history, autocomplete
- **Connection resilience** — Handle network interrupts/reconnects gracefully; add timeouts and retry logic

## LLM
- **OpenAI / local LLM adapter** — Extract abstraction when second provider is needed
- **LLM abstraction layer** — Single provider (Anthropic) for now

## Infrastructure
- **Async conversion** — Add when SAQ task queue is introduced
- **SAQ + Redis task queue** — For background radar polling
- **Full observability** — `platform_operations`, `pipeline_metrics_daily` tables (Phase 5)

## Features
- **Scheduled publishing** — MVP is manual only
- **Auto-engagement** — Requires more trust in agents before automating
- **`blah stats` commands** — Metrics/cost dashboard (Phase 5)
- **Research Agent as separate generator-critic** — MVP does single-pass triage
- **Multi-user support** — Single-user tool for now
