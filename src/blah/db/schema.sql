-- Blah MVP schema

-- Rant flow
CREATE TABLE IF NOT EXISTS rants (
    id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    status TEXT CHECK(status IN ('draft', 'active', 'complete')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pieces (
    id TEXT PRIMARY KEY,
    rant_id TEXT REFERENCES rants(id),
    platform TEXT NOT NULL,
    content TEXT NOT NULL,
    target JSON,
    scheduled_at TIMESTAMP,
    status TEXT CHECK(status IN ('draft', 'approved', 'scheduled', 'publishing', 'published', 'failed')),
    external_id TEXT,
    external_url TEXT,
    published_at TIMESTAMP,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    manual_override JSON
);

CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    type TEXT CHECK(type IN ('image', 'video', 'doc', 'url')),
    location TEXT NOT NULL
);

-- Link tables for resources
CREATE TABLE IF NOT EXISTS rant_resources (
    rant_id TEXT REFERENCES rants(id),
    resource_id TEXT REFERENCES resources(id),
    PRIMARY KEY (rant_id, resource_id)
);

CREATE TABLE IF NOT EXISTS piece_resources (
    piece_id TEXT REFERENCES pieces(id),
    resource_id TEXT REFERENCES resources(id),
    PRIMARY KEY (piece_id, resource_id)
);

-- Radar flow
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    type TEXT NOT NULL,
    config JSON NOT NULL,
    state JSON DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS feed_items (
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

CREATE INDEX IF NOT EXISTS idx_feed_items_status ON feed_items(status);
CREATE INDEX IF NOT EXISTS idx_feed_items_author ON feed_items(author);
CREATE INDEX IF NOT EXISTS idx_feed_items_score ON feed_items(relevance_score);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT CHECK(status IN ('pending', 'in_review', 'complete')),
    sources_polled JSON
);

CREATE TABLE IF NOT EXISTS report_items (
    id TEXT PRIMARY KEY,
    report_id TEXT REFERENCES reports(id),
    type TEXT CHECK(type IN ('signal', 'suggested_follow', 'trending_topic')),
    data JSON NOT NULL,
    relevance_score REAL,
    status TEXT CHECK(status IN ('new', 'reviewed', 'actioned', 'skipped')),
    outcome TEXT
);

-- Chat histories
CREATE TABLE IF NOT EXISTS chat_histories (
    id TEXT PRIMARY KEY,
    messages JSON NOT NULL DEFAULT '[]'
);
