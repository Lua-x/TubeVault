"""library

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 20:00:50.723491
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db
from app.services.search import create_search_index, drop_search_index

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_playlists_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlists")),
    )
    with op.batch_alter_table("playlists", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_playlists_user_id"), ["user_id"], unique=False)

    op.create_table(
        "playlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["playlists.id"],
            name=op.f("fk_playlist_items_playlist_id_playlists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_playlist_items_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlist_items")),
        sa.UniqueConstraint("playlist_id", "video_id", name=op.f("uq_playlist_items_playlist_id")),
    )
    with op.batch_alter_table("playlist_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_playlist_items_playlist_id"), ["playlist_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_playlist_items_video_id"), ["video_id"], unique=False)

    op.create_table(
        "sponsor_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("uuid", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("start_s", sa.Double(), nullable=False),
        sa.Column("end_s", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_sponsor_segments_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sponsor_segments")),
        sa.UniqueConstraint("video_id", "uuid", name=op.f("uq_sponsor_segments_video_id")),
    )
    with op.batch_alter_table("sponsor_segments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sponsor_segments_video_id"), ["video_id"], unique=False
        )

    op.create_table(
        "watch_progress",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("position_s", sa.Double(), nullable=False),
        sa.Column("watched", sa.Boolean(), nullable=False),
        sa.Column("watched_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_watch_progress_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_watch_progress_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "video_id", name=op.f("pk_watch_progress")),
    )
    with op.batch_alter_table("watch_progress", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_watch_progress_updated_at"), ["updated_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_watch_progress_video_id"), ["video_id"], unique=False)

    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.add_column(sa.Column("artwork_checked_at", app.db.UTCDateTime(), nullable=True))

    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sponsorblock_fetched_at", app.db.UTCDateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("sponsorblock_cut", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # After the batch alter of `videos` (which recreates the table and drops its triggers).
    # Any later migration that batch-alters videos or channels must call this again.
    create_search_index(op.get_bind())


def downgrade() -> None:
    drop_search_index(op.get_bind())
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_column("sponsorblock_cut")
        batch_op.drop_column("sponsorblock_fetched_at")

    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.drop_column("artwork_checked_at")

    with op.batch_alter_table("watch_progress", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_watch_progress_video_id"))
        batch_op.drop_index(batch_op.f("ix_watch_progress_updated_at"))

    op.drop_table("watch_progress")
    with op.batch_alter_table("sponsor_segments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sponsor_segments_video_id"))

    op.drop_table("sponsor_segments")
    with op.batch_alter_table("playlist_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_playlist_items_video_id"))
        batch_op.drop_index(batch_op.f("ix_playlist_items_playlist_id"))

    op.drop_table("playlist_items")
    with op.batch_alter_table("playlists", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_playlists_user_id"))

    op.drop_table("playlists")
