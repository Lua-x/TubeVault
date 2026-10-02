"""Full-text search over title, description and channel name (SQLite FTS5).

The index is a separate FTS5 table kept up to date by triggers, so every code path that
changes videos or channel names updates it automatically. Other databases fall back to LIKE.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import Connection, Engine, text

log = logging.getLogger(__name__)

FTS_TABLE = "videos_fts"
MAX_TOKENS = 12
MAX_RESULTS = 1000

_DDL = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5("
    "title, description, channel, tokenize='unicode61 remove_diacritics 2')",
    """CREATE TRIGGER IF NOT EXISTS videos_fts_ai AFTER INSERT ON videos BEGIN
        INSERT INTO videos_fts(rowid, title, description, channel) VALUES (new.id, new.title,
            coalesce(new.description, ''),
            coalesce((SELECT name FROM channels WHERE id = new.channel_id), ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS videos_fts_ad AFTER DELETE ON videos BEGIN
        DELETE FROM videos_fts WHERE rowid = old.id;
    END""",
    """CREATE TRIGGER IF NOT EXISTS videos_fts_au AFTER UPDATE OF title, description, channel_id
        ON videos BEGIN
        DELETE FROM videos_fts WHERE rowid = old.id;
        INSERT INTO videos_fts(rowid, title, description, channel) VALUES (new.id, new.title,
            coalesce(new.description, ''),
            coalesce((SELECT name FROM channels WHERE id = new.channel_id), ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS channels_fts_au AFTER UPDATE OF name ON channels BEGIN
        UPDATE videos_fts SET channel = new.name
        WHERE rowid IN (SELECT id FROM videos WHERE channel_id = new.id);
    END""",
]
_TRIGGERS = ("videos_fts_ai", "videos_fts_ad", "videos_fts_au", "channels_fts_au")


def is_sqlite(conn: Connection) -> bool:
    return conn.dialect.name == "sqlite"


def rebuild(conn: Connection) -> None:
    conn.execute(text("DELETE FROM videos_fts"))
    conn.execute(
        text(
            "INSERT INTO videos_fts(rowid, title, description, channel) "
            "SELECT v.id, v.title, coalesce(v.description, ''), coalesce(c.name, '') "
            "FROM videos v LEFT JOIN channels c ON c.id = v.channel_id"
        )
    )


def create_search_index(conn: Connection) -> None:
    """Create table and triggers (idempotent) and fill the index."""
    if not is_sqlite(conn):
        return
    for statement in _DDL:
        conn.execute(text(statement))
    rebuild(conn)


def drop_search_index(conn: Connection) -> None:
    if not is_sqlite(conn):
        return
    for trigger in _TRIGGERS:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
    conn.execute(text("DROP TABLE IF EXISTS videos_fts"))


def ensure_search_index(engine: Engine) -> None:
    """Safety net: SQLite batch migrations recreate tables and silently drop their triggers."""
    with engine.begin() as conn:
        if not is_sqlite(conn):
            return
        present = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')")
            )
        }
        if FTS_TABLE in present and all(t in present for t in _TRIGGERS):
            return
        log.info("Suchindex wird neu aufgebaut")
        create_search_index(conn)


def fts_query(raw: str) -> str | None:
    """Turn user input into an FTS5 query: every word as a prefix, all words required."""
    tokens = re.findall(r"\w+", raw.lower())[:MAX_TOKENS]
    if not tokens:
        return None
    return " AND ".join(f'"{token}"*' for token in tokens)


def search_ids(conn: Connection, raw: str, limit: int = MAX_RESULTS) -> list[int] | None:
    """Matching video ids, best first. None if full-text search is unavailable."""
    if not is_sqlite(conn):
        return None
    query = fts_query(raw)
    if query is None:
        return []
    rows = conn.execute(
        text(
            "SELECT rowid FROM videos_fts WHERE videos_fts MATCH :query "
            "ORDER BY bm25(videos_fts, 10.0, 1.0, 5.0) LIMIT :limit"
        ),
        {"query": query, "limit": limit},
    )
    return [int(row[0]) for row in rows]
