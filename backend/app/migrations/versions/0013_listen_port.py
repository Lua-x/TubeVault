"""remember the old port for installs from before 1.0

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-05 18:00:00.000000

The default port moved from 8096 (Jellyfin's) to 8823. A database that already has users
was used with 8096 – it keeps that port unless PORT is set (see app/core/ports.py).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM users LIMIT 1")).first() is None:
        return  # a new install: the new default port
    settings = sa.table(
        "settings",
        sa.column("key", sa.String),
        sa.column("value", sa.JSON),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        settings,
        [
            {
                "key": "server",
                "value": {"legacy_port": 8096},
                "updated_at": datetime.now(UTC).replace(tzinfo=None),
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM settings WHERE key = 'server'"))
