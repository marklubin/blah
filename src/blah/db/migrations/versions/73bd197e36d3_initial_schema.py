"""initial schema

Revision ID: 73bd197e36d3
Revises:
Create Date: 2026-02-04 10:36:16.625215

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73bd197e36d3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all initial tables."""
    # Rant flow
    op.execute("""
        CREATE TABLE rants (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            status TEXT CHECK(status IN ('draft', 'active', 'complete')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE pieces (
            id TEXT PRIMARY KEY,
            rant_id TEXT REFERENCES rants(id),
            platform TEXT NOT NULL,
            content TEXT NOT NULL,
            target JSON,
            scheduled_at TIMESTAMP,
            status TEXT CHECK(status IN (
                'draft', 'approved', 'scheduled', 'publishing', 'published', 'failed'
            )),
            external_id TEXT,
            external_url TEXT,
            published_at TIMESTAMP,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            manual_override JSON
        )
    """)

    op.execute("""
        CREATE TABLE resources (
            id TEXT PRIMARY KEY,
            type TEXT CHECK(type IN ('image', 'video', 'doc', 'url')),
            location TEXT NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE rant_resources (
            rant_id TEXT REFERENCES rants(id),
            resource_id TEXT REFERENCES resources(id),
            PRIMARY KEY (rant_id, resource_id)
        )
    """)

    op.execute("""
        CREATE TABLE piece_resources (
            piece_id TEXT REFERENCES pieces(id),
            resource_id TEXT REFERENCES resources(id),
            PRIMARY KEY (piece_id, resource_id)
        )
    """)

    # Radar flow
    op.execute("""
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            type TEXT NOT NULL,
            config JSON NOT NULL,
            state JSON DEFAULT '{}',
            enabled BOOLEAN DEFAULT TRUE
        )
    """)

    op.execute("""
        CREATE TABLE reports (
            id TEXT PRIMARY KEY,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT CHECK(status IN ('pending', 'in_review', 'complete')),
            sources_polled JSON
        )
    """)

    op.execute("""
        CREATE TABLE feed_items (
            id TEXT PRIMARY KEY,
            source_id TEXT REFERENCES sources(id),
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            url TEXT,
            author TEXT,
            content TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT CHECK(status IN (
                'raw', 'triaged', 'researched', 'reported', 'discarded'
            )),
            relevance_score REAL,
            triage_reason TEXT,
            enrichment JSON,
            report_id TEXT REFERENCES reports(id)
        )
    """)

    op.execute("CREATE INDEX idx_feed_items_status ON feed_items(status)")
    op.execute("CREATE INDEX idx_feed_items_author ON feed_items(author)")
    op.execute("CREATE INDEX idx_feed_items_score ON feed_items(relevance_score)")

    op.execute("""
        CREATE TABLE report_items (
            id TEXT PRIMARY KEY,
            report_id TEXT REFERENCES reports(id),
            type TEXT CHECK(type IN ('signal', 'suggested_follow', 'trending_topic')),
            data JSON NOT NULL,
            relevance_score REAL,
            status TEXT CHECK(status IN ('new', 'reviewed', 'actioned', 'skipped')),
            outcome TEXT
        )
    """)

    # Chat histories
    op.execute("""
        CREATE TABLE chat_histories (
            id TEXT PRIMARY KEY,
            messages JSON NOT NULL DEFAULT '[]'
        )
    """)


def downgrade() -> None:
    """Drop all tables."""
    op.execute("DROP TABLE IF EXISTS chat_histories")
    op.execute("DROP TABLE IF EXISTS report_items")
    op.execute("DROP TABLE IF EXISTS feed_items")
    op.execute("DROP TABLE IF EXISTS reports")
    op.execute("DROP TABLE IF EXISTS sources")
    op.execute("DROP TABLE IF EXISTS piece_resources")
    op.execute("DROP TABLE IF EXISTS rant_resources")
    op.execute("DROP TABLE IF EXISTS resources")
    op.execute("DROP TABLE IF EXISTS pieces")
    op.execute("DROP TABLE IF EXISTS rants")
