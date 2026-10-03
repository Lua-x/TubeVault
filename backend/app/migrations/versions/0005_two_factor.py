"""two-factor login

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN (no batch): rebuilding the table would lose the expression index.
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", app.db.UTCDateTime(), nullable=True))
    op.add_column("users", sa.Column("totp_last_counter", sa.Integer(), nullable=True))
    op.add_column(
        "users", sa.Column("recovery_codes", sa.JSON(), nullable=False, server_default="[]")
    )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("recovery_codes")
        batch_op.drop_column("totp_last_counter")
        batch_op.drop_column("totp_enabled_at")
        batch_op.drop_column("totp_secret")
