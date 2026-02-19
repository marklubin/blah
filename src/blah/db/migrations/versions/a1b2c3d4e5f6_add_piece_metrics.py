"""add piece_metrics table

Revision ID: a1b2c3d4e5f6
Revises: 48d354e6dfad
Create Date: 2026-02-18 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "48d354e6dfad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create piece_metrics table."""
    op.execute("""
        CREATE TABLE piece_metrics (
            id TEXT PRIMARY KEY,
            piece_id TEXT NOT NULL REFERENCES pieces(id),
            platform TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            like_count INTEGER DEFAULT 0,
            repost_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            raw_data JSON
        )
    """)
    op.execute("CREATE INDEX idx_piece_metrics_piece_id ON piece_metrics(piece_id)")


def downgrade() -> None:
    """Drop piece_metrics table."""
    op.execute("DROP TABLE IF EXISTS piece_metrics")
