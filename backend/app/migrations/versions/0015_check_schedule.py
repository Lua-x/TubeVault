"""subscriptions: check on chosen weekdays at a set time

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-06 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain columns: no table rebuild (see 0007). Empty = the interval as before.
    op.add_column("subscriptions", sa.Column("check_days", sa.JSON(), nullable=True))
    op.add_column("subscriptions", sa.Column("check_time", sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_column("check_time")
        batch_op.drop_column("check_days")
