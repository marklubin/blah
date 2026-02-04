# Deferred Features

Features explicitly out of scope for MVP and why.

## Platform Adapters
- **Mastodon adapter** — Add after Twitter is stable
- **Reddit / Threads / HN / LinkedIn adapters** — Different content styles, API approval overhead
- **Browser fallback adapter** — Only needed for platforms without write APIs

## Chat UI
- **prompt_toolkit chat UI** — Upgrade from `input()` later for readline, history, autocomplete

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
