"""subscriptions

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02 19:14:24.079627
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("channel", "playlist", name="subscriptionkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("youtube_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("last_checked_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("next_check_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("last_check_error", sa.Text(), nullable=True),
        sa.Column("backfill", sa.Integer(), nullable=True),
        sa.Column("include_shorts", sa.Boolean(), nullable=False),
        sa.Column("include_live", sa.Boolean(), nullable=False),
        sa.Column("min_duration_s", sa.Integer(), nullable=True),
        sa.Column("max_duration_s", sa.Integer(), nullable=True),
        sa.Column("date_after", sa.Date(), nullable=True),
        sa.Column("download_options", sa.JSON(), nullable=False),
        sa.Column("keep_days", sa.Integer(), nullable=True),
        sa.Column("keep_last", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_subscriptions_channel_id_channels"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_subscriptions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("kind", "youtube_id", name=op.f("uq_subscriptions_kind")),
    )
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_subscriptions_channel_id"), ["channel_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_subscriptions_next_check_at"), ["next_check_at"], unique=False
        )

    op.create_table(
        "subscription_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("youtube_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("upload_date", sa.Date(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "queued",
                "downloaded",
                "filtered",
                "skipped",
                "failed",
                "removed",
                name="itemstate",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("video_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["download_jobs.id"],
            name=op.f("fk_subscription_items_job_id_download_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_subscription_items_subscription_id_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_subscription_items_video_id_videos"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_items")),
        sa.UniqueConstraint(
            "subscription_id", "youtube_id", name=op.f("uq_subscription_items_subscription_id")
        ),
    )
    with op.batch_alter_table("subscription_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subscription_items_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_subscription_items_subscription_id"), ["subscription_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_subscription_items_video_id"), ["video_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_subscription_items_youtube_id"), ["youtube_id"], unique=False
        )

    with op.batch_alter_table("download_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subscription_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_download_jobs_subscription_id"), ["subscription_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_download_jobs_subscription_id_subscriptions"),
            "subscriptions",
            ["subscription_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Everything in the library so far was added by hand.
    op.execute(sa.text("UPDATE videos SET manual = :yes").bindparams(yes=True))


def downgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_column("manual")

    with op.batch_alter_table("download_jobs", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_download_jobs_subscription_id_subscriptions"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_download_jobs_subscription_id"))
        batch_op.drop_column("subscription_id")

    with op.batch_alter_table("subscription_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscription_items_youtube_id"))
        batch_op.drop_index(batch_op.f("ix_subscription_items_video_id"))
        batch_op.drop_index(batch_op.f("ix_subscription_items_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_subscription_items_state"))

    op.drop_table("subscription_items")
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscriptions_next_check_at"))
        batch_op.drop_index(batch_op.f("ix_subscriptions_channel_id"))

    op.drop_table("subscriptions")
