"""comments saved with videos (optional)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("youtube_id", sa.String(length=128), nullable=False),
        sa.Column("parent_id", sa.String(length=128), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("author_is_uploader", sa.Boolean(), nullable=False),
        sa.Column("author_is_verified", sa.Boolean(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("published_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("is_favorited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_video_id", "comments", ["video_id"])
    # Plain columns: SQLite adds them in place (no table rebuild).
    op.add_column("videos", sa.Column("comments_fetched_at", app.db.UTCDateTime(), nullable=True))
    op.add_column("videos", sa.Column("comment_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_column("comment_count")
        batch_op.drop_column("comments_fetched_at")
    op.drop_index("ix_comments_video_id", table_name="comments")
    op.drop_table("comments")
