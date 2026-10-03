"""the built-in "Später ansehen" playlist

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-04 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "playlists",
        sa.Column("is_watch_later", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_playlists_watch_later",
        "playlists",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("is_watch_later = 1"),
    )


def downgrade() -> None:
    op.drop_index("ix_playlists_watch_later", table_name="playlists")
    with op.batch_alter_table("playlists", schema=None) as batch_op:
        batch_op.drop_column("is_watch_later")
