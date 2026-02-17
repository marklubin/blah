"""add suggestions table

Revision ID: 48d354e6dfad
Revises: 73bd197e36d3
Create Date: 2026-02-06 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "48d354e6dfad"
down_revision: str | Sequence[str] | None = "73bd197e36d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create suggestions table."""
    op.execute("""
        CREATE TABLE suggestions (
            id TEXT PRIMARY KEY,
            idea TEXT NOT NULL,
            source TEXT DEFAULT 'api',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'queued'
                CHECK(status IN ('queued', 'reviewed', 'converted', 'dismissed')),
            rant_id TEXT REFERENCES rants(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX idx_suggestions_status ON suggestions(status)")


def downgrade() -> None:
    """Drop suggestions table."""
    op.execute("DROP TABLE IF EXISTS suggestions")
