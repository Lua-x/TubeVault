"""best available quality as the default

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-05 21:00:00.000000

Downloads used to stop at 1080p unless set otherwise. Now the default is the best available
quality, like the highest Pinchflat profile. An install still on the old default moves along;
any other limit was chosen on purpose and stays, and so do the subscriptions' own limits.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DEFAULT = 1080

settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.JSON))


def upgrade() -> None:
    bind = op.get_bind()
    value: Any = bind.execute(
        sa.select(settings.c.value).where(settings.c.key == "app")
    ).scalar_one_or_none()
    if not isinstance(value, dict):
        return  # never saved: the new default applies by itself
    downloads = value.get("downloads")
    if not isinstance(downloads, dict) or downloads.get("max_height") != OLD_DEFAULT:
        return
    value = {**value, "downloads": {**downloads, "max_height": None}}
    bind.execute(settings.update().where(settings.c.key == "app").values(value=value))


def downgrade() -> None:
    pass  # "best available" is a valid setting in older versions too
