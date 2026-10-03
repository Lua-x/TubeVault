"""what each user may see and do

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-03 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("channel_access", sa.String(length=16), nullable=False, server_default="all")
        )
        batch_op.add_column(
            sa.Column("may_add", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    op.create_table(
        "user_channels",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_user_channels_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_channels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "channel_id", name=op.f("pk_user_channels")),
    )


def downgrade() -> None:
    op.drop_table("user_channels")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("may_add")
        batch_op.drop_column("channel_access")
