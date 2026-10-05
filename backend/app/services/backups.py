"""Backups of the database: everything except the video files themselves.

All settings, users, subscriptions, playlists and watch progress live in the SQLite
database, so a backup is a consistent copy of it (SQLite's online backup, safe while
TubeVault runs) plus a small manifest, zipped. Videos, thumbnails and subtitles stay
in /media and are not part of it.

Restoring never swaps the database under a running server: the archive is checked and
staged, and the next start puts it in place before the database is opened – after
backing up the current state, so a restore can always be undone.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory

from app import __version__
from app.config import Settings
from app.migrate import MIGRATIONS_DIR

log = logging.getLogger(__name__)

DB_NAME = "tubevault.db"
MANIFEST = "backup.json"
NAME_RE = re.compile(r"^tubevault-backup-(\d{8}-\d{6})(-auto)?\.zip$")
MAX_UPLOAD_BYTES = 4 * 1024**3
# Unpacked: a real database is a few hundred MB at most – this stops "zip bombs".
MAX_DATABASE_BYTES = 16 * 1024**3
SPARE_BYTES = 200 * 1024**2
AUTO_INTERVAL = timedelta(hours=23)  # daily, a little early so the time doesn't drift


class BackupError(Exception):
    """A backup could not be created, read or restored – the message says why (German)."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    name: str
    size: int
    created_at: datetime
    auto: bool


def backups_dir(settings: Settings) -> Path:
    return settings.config_dir / "backups"


def staging_dir(settings: Settings) -> Path:
    return settings.config_dir / ".restore"


def database_path(settings: Settings) -> Path:
    url = settings.db_url
    if not url.startswith("sqlite:///"):
        raise BackupError("Sicherungen gibt es nur für die eingebaute SQLite-Datenbank.")
    return Path(url.removeprefix("sqlite:///"))


def _info(path: Path) -> BackupInfo | None:
    match = NAME_RE.match(path.name)
    if not match:
        return None
    created = datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    return BackupInfo(path.name, path.stat().st_size, created, bool(match.group(2)))


def list_backups(settings: Settings) -> list[BackupInfo]:
    folder = backups_dir(settings)
    if not folder.is_dir():
        return []
    infos = [info for path in folder.iterdir() if (info := _info(path))]
    return sorted(infos, key=lambda info: info.created_at, reverse=True)


def backup_path(settings: Settings, name: str) -> Path:
    """The file of a listed backup; names are checked, so no path tricks."""
    if not NAME_RE.match(name):
        raise BackupError("Unbekannte Sicherung.")
    path = backups_dir(settings) / name
    if not path.is_file():
        raise BackupError("Diese Sicherung gibt es nicht mehr.")
    return path


def _known_revisions() -> set[str]:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return {rev.revision for rev in ScriptDirectory.from_config(config).walk_revisions()}


def _summary(db: sqlite3.Connection) -> dict[str, Any]:
    def count(table: str) -> int:
        try:
            return int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
        except sqlite3.Error:
            return 0

    revision = db.execute("SELECT version_num FROM alembic_version").fetchone()
    return {
        "schema": revision[0] if revision else None,
        "videos": count("videos"),
        "subscriptions": count("subscriptions"),
        "users": count("users"),
    }


def create_backup(settings: Settings, *, auto: bool = False) -> BackupInfo:
    source = database_path(settings)
    folder = backups_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).replace(microsecond=0)
    while True:  # two backups within one second must not overwrite each other
        name = f"tubevault-backup-{now:%Y%m%d-%H%M%S}{'-auto' if auto else ''}.zip"
        target = folder / name
        if not target.exists():
            break
        now += timedelta(seconds=1)
    snapshot = folder / f".{name}.db"
    try:
        with (
            closing(sqlite3.connect(source)) as live,
            closing(sqlite3.connect(snapshot)) as copy,
        ):
            live.backup(copy)  # consistent, even while downloads write to the database
            manifest = {
                "app": "TubeVault",
                "version": __version__,
                "created_at": now.isoformat(),
                **_summary(copy),
            }
        partial = target.with_suffix(".part")
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, DB_NAME)
            archive.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
        partial.replace(target)
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(f"Sicherung fehlgeschlagen: {exc}") from exc
    finally:
        snapshot.unlink(missing_ok=True)
        target.with_suffix(".part").unlink(missing_ok=True)
    log.info("Sicherung erstellt: %s", name)
    info = _info(target)
    assert info is not None
    return info


def prune_auto_backups(settings: Settings, keep: int) -> int:
    """Keep the newest `keep` automatic backups; manual ones stay until deleted."""
    autos = [info for info in list_backups(settings) if info.auto]
    for info in autos[keep:]:
        (backups_dir(settings) / info.name).unlink(missing_ok=True)
    return max(len(autos) - keep, 0)


def auto_backup_if_due(settings: Settings, keep: int) -> BackupInfo | None:
    latest = next((info for info in list_backups(settings) if info.auto), None)
    if latest and datetime.now(UTC) - latest.created_at < AUTO_INTERVAL:
        return None
    info = create_backup(settings, auto=True)
    prune_auto_backups(settings, keep)
    return info


def delete_backup(settings: Settings, name: str) -> None:
    backup_path(settings, name).unlink()


# --- restore -----------------------------------------------------------------------


@contextmanager
def _open_archive(path: Path) -> Iterator[zipfile.ZipFile]:
    try:
        with zipfile.ZipFile(path) as archive:
            yield archive
    except zipfile.BadZipFile as exc:
        raise BackupError("Das ist keine TubeVault-Sicherung (keine ZIP-Datei).") from exc


def check_archive(path: Path, extract_to: Path) -> dict[str, Any]:
    """Validate a backup and extract its database. Returns the manifest."""
    with _open_archive(path) as archive:
        names = set(archive.namelist())
        if not {DB_NAME, MANIFEST} <= names:
            raise BackupError("Das ist keine TubeVault-Sicherung (Datenbank fehlt).")
        try:
            manifest = json.loads(archive.read(MANIFEST))
        except ValueError as exc:
            raise BackupError("Die Sicherung ist beschädigt (backup.json).") from exc
        if not isinstance(manifest, dict) or manifest.get("app") != "TubeVault":
            raise BackupError("Das ist keine TubeVault-Sicherung.")
        extract_to.parent.mkdir(parents=True, exist_ok=True)
        # The size in the archive bounds what reading it can produce.
        size = archive.getinfo(DB_NAME).file_size
        if size > MAX_DATABASE_BYTES:
            raise BackupError("Die Datenbank in der Sicherung ist unplausibel groß.")
        if size + SPARE_BYTES > shutil.disk_usage(extract_to.parent).free:
            raise BackupError("Nicht genug freier Speicher, um die Sicherung einzuspielen.")
        with archive.open(DB_NAME) as source, extract_to.open("wb") as target:
            shutil.copyfileobj(source, target)

    try:
        with closing(sqlite3.connect(f"file:{extract_to}?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError("Die Datenbank in der Sicherung ist beschädigt.")
            summary = _summary(db)
    except sqlite3.Error as exc:
        raise BackupError(f"Die Datenbank in der Sicherung ist unlesbar: {exc}") from exc
    if summary["schema"] not in _known_revisions():
        raise BackupError(
            "Diese Sicherung stammt von einer neueren TubeVault-Version. "
            "Bitte erst TubeVault aktualisieren."
        )
    return {**manifest, **summary}


def stage_restore(settings: Settings, archive: Path) -> dict[str, Any]:
    """Check the archive and put its database aside for the next start."""
    folder = staging_dir(settings)
    shutil.rmtree(folder, ignore_errors=True)
    try:
        manifest = check_archive(archive, folder / DB_NAME)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    (folder / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    log.info("Wiederherstellung vorbereitet (Stand %s)", manifest.get("created_at"))
    return manifest


def cancel_restore(settings: Settings) -> None:
    shutil.rmtree(staging_dir(settings), ignore_errors=True)


def staged_restore(settings: Settings) -> dict[str, Any] | None:
    manifest = staging_dir(settings) / MANIFEST
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def apply_staged_restore(settings: Settings) -> bool:
    """At startup, before the database is opened: swap in a staged backup."""
    folder = staging_dir(settings)
    staged = folder / DB_NAME
    if not staged.is_file():
        return False
    target = database_path(settings)
    if target.exists():
        # The current state becomes a regular backup, so the restore can be undone.
        create_backup(settings)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(staged, target)
    shutil.rmtree(folder, ignore_errors=True)
    log.warning("Datenbank aus einer Sicherung wiederhergestellt")
    return True
