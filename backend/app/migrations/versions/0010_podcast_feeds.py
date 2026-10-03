"""podcast feed token per user

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-04 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain column and unique index: no table rebuild (see 0007).
    op.add_column("users", sa.Column("feed_token", sa.String(length=64), nullable=True))
    op.create_index("ix_users_feed_token", "users", ["feed_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_feed_token", table_name="users")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("feed_token")
