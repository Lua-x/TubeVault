"""media analysis: loudness and seek previews per video

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain columns: no table rebuild (see 0007).
    op.add_column("videos", sa.Column("loudness_lufs", sa.Float(), nullable=True))
    op.add_column("videos", sa.Column("loudness_at", sa.DateTime(), nullable=True))
    op.add_column("videos", sa.Column("trickplay", sa.JSON(), nullable=True))
    op.add_column("videos", sa.Column("trickplay_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_column("trickplay_at")
        batch_op.drop_column("trickplay")
        batch_op.drop_column("loudness_at")
        batch_op.drop_column("loudness_lufs")
