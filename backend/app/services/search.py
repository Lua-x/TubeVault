"""Full-text search over title, description and channel name (SQLite FTS5).

The index is a separate FTS5 table kept up to date by triggers, so every code path that
changes videos or channel names updates it automatically. Other databases fall back to LIKE.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import CTE, Connection, Engine, Float, Integer, text

log = logging.getLogger(__name__)

FTS_TABLE = "videos_fts"
MAX_TOKENS = 12

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


# Words that say nothing about what a video is about.
_STOPWORD_TEXT = """
aber alle als also am an auch auf aus bei bin bis das dass dem den der des die dies diese
dieser du ein eine einem einen einer es für hat hier ich ihr im in ist ja kann mal man mit
nach nicht noch nur oder schon sich sie sind so über um und uns von vor war was wie wir wird
zu zum zur
a about after all an and are as at be but by can do for from get how i if in is it its my
new not of on or our so that the this to was we what when why will with you your
video videos official part teil folge episode live full hd 4k
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def similar_query(*texts: str) -> str | None:
    """An FTS5 query for videos about the same thing: any of the telling words."""
    words: list[str] = []
    for value in texts:
        for word in re.findall(r"\w+", value.lower()):
            telling = len(word) >= 3 and not word.isdigit() and word not in _STOPWORDS
            if telling and word not in words:
                words.append(word)
    if not words:
        return None
    return " OR ".join(f'"{word}"' for word in words[:MAX_TOKENS])


def _ranking(query: str) -> CTE:
    return (
        text(
            "SELECT rowid AS id, bm25(videos_fts, 10.0, 1.0, 5.0) AS rank "
            "FROM videos_fts WHERE videos_fts MATCH :query"
        )
        .bindparams(query=query)
        .columns(id=Integer, rank=Float)
        .cte("search")
        .prefix_with("MATERIALIZED")
    )


def similar_ranking(conn: Connection, title: str) -> CTE | None:
    """Videos sharing telling words with a title, as (id, rank). None if nothing to go by."""
    if not is_sqlite(conn):
        return None
    query = similar_query(title)
    return _ranking(query) if query else None


def search_ranking(conn: Connection, raw: str) -> CTE | None:
    """Matching videos as (id, rank) – lower rank is better. None without full-text search.

    A query instead of a list of ids, so counting, sorting and paging happen in the
    database – for any number of matches. MATERIALIZED makes SQLite search the index
    once; otherwise it may pick the videos table as the outer loop and search the index
    again for every single video (seconds instead of milliseconds for broad terms).
    """
    if not is_sqlite(conn):
        return None
    return _ranking(fts_query(raw) or '""')  # nothing searchable: matches nothing
