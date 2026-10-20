"""subscriptions: filter by words in the title

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-20 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain columns: no table rebuild (see 0007). Empty = every title, as before.
    op.add_column("subscriptions", sa.Column("title_include", sa.Text(), nullable=True))
    op.add_column("subscriptions", sa.Column("title_exclude", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_column("title_exclude")
        batch_op.drop_column("title_include")
