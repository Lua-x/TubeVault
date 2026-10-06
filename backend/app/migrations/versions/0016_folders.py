"""folders: each account's own folders (with subfolders) for sorting videos

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_folders_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["folders.id"],
            name=op.f("fk_folders_parent_id_folders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folders")),
    )
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_folders_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_folders_parent_id"), ["parent_id"], unique=False)

    op.create_table(
        "folder_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("added_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["folders.id"],
            name=op.f("fk_folder_items_folder_id_folders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_folder_items_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folder_items")),
        sa.UniqueConstraint("folder_id", "video_id", name=op.f("uq_folder_items_folder_id")),
    )
    with op.batch_alter_table("folder_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_folder_items_folder_id"), ["folder_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_folder_items_video_id"), ["video_id"], unique=False)


def downgrade() -> None:
    op.drop_table("folder_items")
    op.drop_table("folders")
