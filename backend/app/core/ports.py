"""Which port TubeVault listens on.

Since 1.0 the default is 8823 ("TUBE" on a phone keypad): 8096 belongs to Jellyfin, and many
run both side by side. Installs from before 1.0 keep 8096 as long as PORT doesn't say
otherwise – an update must never make a running server unreachable. Migration 0013 leaves a
marker for them, so this also holds after the first start of the new version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings

DEFAULT_PORT = 8823
LEGACY_PORT = 8096
MARKER_KEY = "server"
# The first schema that writes the marker; older databases are recognised by their version.
MARKER_REVISION = "0013"

PortSource = Literal["env", "legacy", "default"]


@dataclass(frozen=True)
class ListenPort:
    port: int
    source: PortSource


def resolve_port(settings: Settings) -> ListenPort:
    """PORT if set; 8096 for an install from before 1.0; otherwise 8823."""
    if settings.port is not None:
        return ListenPort(settings.port, "env")
    if legacy_install(settings):
        return ListenPort(LEGACY_PORT, "legacy")
    return ListenPort(DEFAULT_PORT, "default")


def legacy_install(settings: Settings) -> bool:
    """Read before the migrations run; a fresh or unreadable database counts as new."""
    if settings.database_url is None and not (settings.config_dir / "tubevault.db").is_file():
        return False
    engine = create_engine(settings.db_url)
    try:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            if not {"settings", "alembic_version", "users"} <= tables:
                return False
            marker = conn.execute(
                text("SELECT value FROM settings WHERE key = :key"), {"key": MARKER_KEY}
            ).scalar()
            if marker is not None:
                value = json.loads(marker) if isinstance(marker, str) else marker
                return isinstance(value, dict) and value.get("legacy_port") == LEGACY_PORT
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if version is None or str(version) >= MARKER_REVISION:
                return False
            # A database nobody ever signed in to may as well start on the new port.
            return conn.execute(text("SELECT 1 FROM users LIMIT 1")).first() is not None
    except (SQLAlchemyError, ValueError):
        return False
    finally:
        engine.dispose()
