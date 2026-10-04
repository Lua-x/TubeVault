"""family devices and profile PINs

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-05 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain columns on users: no table rebuild (see 0007).
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("on_family_devices", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "family_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_family_devices_token_hash", "family_devices", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_family_devices_token_hash", table_name="family_devices")
    op.drop_table("family_devices")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("on_family_devices")
        batch_op.drop_column("pin_hash")
