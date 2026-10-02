"""Apply database migrations on startup."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

log = logging.getLogger(__name__)


class DatabaseTooNewError(RuntimeError):
    """The database was migrated by a newer TubeVault; downgrades are not supported."""


def run_migrations(engine: Engine) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    known = {rev.revision for rev in ScriptDirectory.from_config(config).walk_revisions()}
    with engine.begin() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
        unknown = sorted(rev for rev in current if rev not in known)
        if unknown:
            message = (
                "Die Datenbank stammt von einer neueren TubeVault-Version "
                f"(Schema {', '.join(unknown)}). Ein Downgrade ist nicht möglich – bitte das "
                "aktuelle Image verwenden oder ein Backup von /config zurückspielen."
            )
            log.critical(message)
            raise DatabaseTooNewError(message)
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
