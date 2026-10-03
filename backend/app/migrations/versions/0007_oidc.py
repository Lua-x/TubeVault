"""link accounts to an OpenID Connect provider

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A unique index, not a constraint: SQLite would rebuild the table for a constraint
    # and lose the expression index on lower(username).
    op.add_column("users", sa.Column("oidc_subject", sa.String(length=255), nullable=True))
    op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"], unique=True)
    # An early build of 0006 rebuilt the users table and dropped this index; bring it back.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_lower ON users (lower(username))"
    )


def downgrade() -> None:
    op.drop_index("ix_users_oidc_subject", table_name="users")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("oidc_subject")
