"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-02 16:12:17.886307
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("youtube_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("folder_name", sa.String(length=255), nullable=False),
        sa.Column("avatar_path", sa.String(length=1024), nullable=True),
        sa.Column("banner_path", sa.String(length=1024), nullable=True),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("folder_name", name=op.f("uq_channels_folder_name")),
        sa.UniqueConstraint("youtube_id", name=op.f("uq_channels_youtube_id")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("last_login_at", app.db.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("ix_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("expires_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("last_seen_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("youtube_id", sa.String(length=64), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("upload_date", sa.Date(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("is_short", sa.Boolean(), nullable=False),
        sa.Column("was_live", sa.Boolean(), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "downloading",
                "ready",
                "failed",
                "missing",
                name="videostatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=1024), nullable=True),
        sa.Column("filesize", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("vcodec", sa.String(length=64), nullable=True),
        sa.Column("acodec", sa.String(length=64), nullable=True),
        sa.Column("chapters", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("added_by_id", sa.Integer(), nullable=True),
        sa.Column("added_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("downloaded_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            name=op.f("fk_videos_added_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_videos_channel_id_channels"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
        sa.UniqueConstraint("youtube_id", name=op.f("uq_videos_youtube_id")),
    )
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_videos_added_at"), ["added_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_videos_channel_id"), ["channel_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_videos_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_videos_upload_date"), ["upload_date"], unique=False)

    op.create_table(
        "download_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("youtube_id", sa.String(length=64), nullable=True),
        sa.Column("video_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "paused",
                "completed",
                "failed",
                "cancelled",
                name="jobstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.Enum(
                "metadata",
                "downloading",
                "postprocessing",
                name="jobstage",
                native_enum=False,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("progress", sa.Double(), nullable=False),
        sa.Column("downloaded_bytes", sa.BigInteger(), nullable=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("speed", sa.Double(), nullable=True),
        sa.Column("eta", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", app.db.UTCDateTime(), nullable=True),
        sa.Column(
            "error_kind",
            sa.Enum(
                "network",
                "rate_limited",
                "unavailable",
                "live",
                "unknown",
                name="errorkind",
                native_enum=False,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("finished_at", app.db.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_download_jobs_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_download_jobs_video_id_videos"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_jobs")),
    )
    with op.batch_alter_table("download_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_download_jobs_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_download_jobs_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_download_jobs_video_id"), ["video_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_download_jobs_youtube_id"), ["youtube_id"], unique=False
        )

    op.create_table(
        "subtitles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("is_auto", sa.Boolean(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_subtitles_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subtitles")),
        sa.UniqueConstraint("video_id", "lang", "is_auto", name=op.f("uq_subtitles_video_id")),
    )
    with op.batch_alter_table("subtitles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subtitles_video_id"), ["video_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("subtitles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subtitles_video_id"))

    op.drop_table("subtitles")
    with op.batch_alter_table("download_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_download_jobs_youtube_id"))
        batch_op.drop_index(batch_op.f("ix_download_jobs_video_id"))
        batch_op.drop_index(batch_op.f("ix_download_jobs_status"))
        batch_op.drop_index(batch_op.f("ix_download_jobs_created_at"))

    op.drop_table("download_jobs")
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_videos_upload_date"))
        batch_op.drop_index(batch_op.f("ix_videos_status"))
        batch_op.drop_index(batch_op.f("ix_videos_channel_id"))
        batch_op.drop_index(batch_op.f("ix_videos_added_at"))

    op.drop_table("videos")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))

    op.drop_table("sessions")
    op.drop_index("ix_users_username_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("settings")
    op.drop_table("channels")
