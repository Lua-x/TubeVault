from __future__ import annotations

import warnings

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool
from sqlalchemy.exc import SAWarning

import app.models  # noqa: F401 – registers all tables
from app.config import Settings
from app.db import Base

config = context.config

# SQLite batch migrations reflect related tables; the case-insensitive username index is
# an expression index SQLAlchemy cannot reflect. It is recreated unchanged, so stay quiet.
warnings.filterwarnings(
    "ignore", message="Skipped unsupported reflection of expression-based index", category=SAWarning
)
target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or Settings().db_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    section = config.get_section(config.config_ini_section, {})
    section.setdefault("sqlalchemy.url", Settings().db_url)
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
