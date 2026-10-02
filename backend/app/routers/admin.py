"""Admin dashboard: statistics, logs, yt-dlp updates, restart and maintenance."""

from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import sqlite3
import urllib.request
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app import __version__
from app.core.deps import AdminUser, Context, DbSession
from app.core.lifecycle import request_restart, uptime_s
from app.models import (
    ACTIVE_JOB_STATUSES,
    Channel,
    DownloadJob,
    JobStatus,
    Subscription,
    SubscriptionKind,
    Video,
    VideoStatus,
)
from app.routers.system import ffmpeg_version
from app.services.app_settings import load_app_settings
from app.services.catalog import channel_url
from app.services.search import is_sqlite, rebuild
from app.services.subscriptions import store_channel_art
from app.services.videos import video_file_exists
from app.services.ytdlp_updater import (
    _version_in,
    _version_key,
    bundled_version,
    current_ytdlp_version,
    runtime_site_dir,
    update_ytdlp,
)
from app.workers.library_tasks import Progress, TaskBusyError

router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger(__name__)

TOP_CHANNELS = 8
PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
HISTORY_DAYS = 30
_LOG_LINE = re.compile(
    r"^(?P<time>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (?P<level>[A-Z]+)\s+(?P<logger>[^:]+): ?"
    r"(?P<message>.*)$"
)
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class ChannelStorage(BaseModel):
    channel_id: int | None
    name: str
    size: int
    videos: int


class DayCount(BaseModel):
    date: date
    completed: int
    failed: int


class Overview(BaseModel):
    videos: int
    channels: int
    subscriptions: int
    library_size: int
    disk_total: int | None
    disk_free: int | None
    cache_size: int
    database_size: int
    downloads_7d: int
    failed_7d: int
    queued: int
    storage_by_channel: list[ChannelStorage]
    downloads_per_day: list[DayCount]
    versions: dict[str, str | None]
    uptime_s: float
    hwaccel: str
    transcode_sessions: int


@router.get("/overview")
def overview(_: AdminUser, db: DbSession, ctx: Context) -> Overview:
    settings = ctx.settings
    ready = Video.status == VideoStatus.READY
    videos = db.scalar(select(func.count()).select_from(Video).where(ready)) or 0
    library_size = db.scalar(select(func.coalesce(func.sum(Video.filesize), 0)).where(ready)) or 0

    rows = db.execute(
        select(
            Video.channel_id,
            Channel.name,
            func.coalesce(func.sum(Video.filesize), 0).label("size"),
            func.count(Video.id).label("videos"),
        )
        .join(Channel, Channel.id == Video.channel_id, isouter=True)
        .where(ready)
        .group_by(Video.channel_id, Channel.name)
        .order_by(func.sum(Video.filesize).desc())
    ).all()
    storage = [
        ChannelStorage(
            channel_id=r.channel_id, name=r.name or "Ohne Kanal", size=r.size, videos=r.videos
        )
        for r in rows
    ]
    if len(storage) > TOP_CHANNELS:
        rest = storage[TOP_CHANNELS - 1 :]
        storage = [
            *storage[: TOP_CHANNELS - 1],
            ChannelStorage(
                channel_id=None,
                name=f"{len(rest)} weitere Kanäle",
                size=sum(c.size for c in rest),
                videos=sum(c.videos for c in rest),
            ),
        ]

    now = datetime.now(UTC)
    since = now - timedelta(days=HISTORY_DAYS)
    finished = db.execute(
        select(DownloadJob.finished_at, DownloadJob.status).where(
            DownloadJob.finished_at >= since,
            DownloadJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
        )
    ).all()
    completed: Counter[date] = Counter()
    failed: Counter[date] = Counter()
    week_ago = now - timedelta(days=7)
    downloads_7d = failed_7d = 0
    for finished_at, job_status in finished:
        if finished_at is None:  # excluded by the query; keeps the type checker happy
            continue
        day = finished_at.astimezone(UTC).date()
        if job_status is JobStatus.COMPLETED:
            completed[day] += 1
            downloads_7d += finished_at >= week_ago
        else:
            failed[day] += 1
            failed_7d += finished_at >= week_ago
    today = now.date()
    days = [today - timedelta(days=offset) for offset in range(HISTORY_DAYS - 1, -1, -1)]

    disk_total = disk_free = None
    try:
        usage = shutil.disk_usage(settings.media_dir)
        disk_total, disk_free = usage.total, usage.free
    except OSError:
        pass
    database = settings.config_dir / "tubevault.db"
    database_size = sum(
        p.stat().st_size for p in (database, database.with_name("tubevault.db-wal")) if p.is_file()
    )
    options = load_app_settings(db).transcoding

    return Overview(
        videos=videos,
        channels=db.scalar(select(func.count(func.distinct(Video.channel_id))).where(ready)) or 0,
        subscriptions=db.scalar(select(func.count()).select_from(Subscription)) or 0,
        library_size=library_size,
        disk_total=disk_total,
        disk_free=disk_free,
        cache_size=ctx.transcoder.cache_size(),
        database_size=database_size,
        downloads_7d=downloads_7d,
        failed_7d=failed_7d,
        queued=db.scalar(
            select(func.count())
            .select_from(DownloadJob)
            .where(DownloadJob.status.in_(ACTIVE_JOB_STATUSES))
        )
        or 0,
        storage_by_channel=storage,
        downloads_per_day=[
            DayCount(date=d, completed=completed[d], failed=failed[d]) for d in days
        ],
        versions={
            "tubevault": __version__,
            "yt-dlp": current_ytdlp_version(),
            "ffmpeg": ffmpeg_version(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        uptime_s=round(uptime_s()),
        hwaccel=options.hwaccel,
        transcode_sessions=len(ctx.transcoder.sessions()),
    )


# --- logs ----------------------------------------------------------------------------


class LogEntry(BaseModel):
    time: str
    level: str
    logger: str
    message: str


@router.get("/logs")
def logs(
    _: AdminUser,
    ctx: Context,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    limit: int = Query(default=300, ge=10, le=2000),
) -> list[LogEntry]:
    path = ctx.settings.logs_dir / "tubevault.log"
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 512 * 1024))
        text = handle.read().decode("utf-8", errors="replace")
    entries: list[LogEntry] = []
    for line in text.splitlines():
        match = _LOG_LINE.match(line)
        if match:
            entries.append(LogEntry(**match.groupdict()))
        elif entries and line.strip():  # traceback lines belong to the entry above
            entries[-1].message += "\n" + line
    wanted = _LEVELS[level]
    return [e for e in entries if _LEVELS.get(e.level, 0) >= wanted][-limit:]


# --- yt-dlp --------------------------------------------------------------------------


class YtDlpInfo(BaseModel):
    loaded: str | None
    installed: str | None
    latest: str | None
    restart_required: bool


def _installed_ytdlp(ctx: Any) -> str | None:
    site = runtime_site_dir(ctx.settings.runtime_dir)
    installed = (_version_in(site) if site.exists() else None) or bundled_version(site)
    loaded = current_ytdlp_version()
    # Same version, written the way yt-dlp writes it (2026.08.19, not 2026.8.19).
    return loaded if installed and not _differs(installed, loaded) else installed


def _differs(installed: str | None, loaded: str | None) -> bool:
    """2026.08.19 (yt-dlp) and 2026.8.19 (package metadata) are the same version."""
    return bool(installed and loaded and _version_key(installed) != _version_key(loaded))


def _latest_ytdlp() -> str | None:
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=10) as response:
            return str(json.load(response)["info"]["version"])
    except (OSError, ValueError, KeyError) as exc:
        log.info("PyPI nicht erreichbar: %s", exc)
        return None


@router.get("/ytdlp")
def ytdlp(_: AdminUser, ctx: Context, check: bool = False) -> YtDlpInfo:
    loaded = current_ytdlp_version()
    installed = _installed_ytdlp(ctx)
    return YtDlpInfo(
        loaded=loaded,
        installed=installed,
        latest=_latest_ytdlp() if check else None,
        restart_required=_differs(installed, loaded),
    )


class YtDlpUpdate(BaseModel):
    updated: bool
    message: str
    info: YtDlpInfo


@router.post("/ytdlp/update")
def ytdlp_update(_: AdminUser, ctx: Context) -> YtDlpUpdate:
    result = update_ytdlp(ctx.settings.runtime_dir)
    loaded = current_ytdlp_version()
    installed = _installed_ytdlp(ctx)
    return YtDlpUpdate(
        updated=result.updated,
        message=result.message,
        info=YtDlpInfo(
            loaded=loaded,
            installed=installed,
            latest=None,
            restart_required=_differs(installed, loaded),
        ),
    )


@router.post("/restart", status_code=status.HTTP_202_ACCEPTED)
def restart(_: AdminUser, ctx: Context) -> dict[str, str]:
    if ctx.library_tasks.busy():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Erst die laufende Aufgabe in der Bibliothek abwarten."
        )
    log.info("Neustart über die Verwaltung angefordert")
    request_restart()
    return {"detail": "TubeVault startet neu"}


# --- maintenance ---------------------------------------------------------------------

Action = Literal["search-index", "artwork", "verify", "nfo", "cache"]
LABELS: dict[str, str] = {
    "search-index": "Suchindex neu aufbauen",
    "artwork": "Kanalbilder neu laden",
    "verify": "Dateien prüfen",
    "nfo": "NFO-Dateien neu schreiben",
    "cache": "Umwandlungs-Cache leeren",
}


@router.post("/maintenance/{action}")
def maintenance(action: Action, _: AdminUser, ctx: Context) -> dict[str, Any]:
    if action == "nfo":
        with ctx.sessions() as db:
            options = load_app_settings(db).library
        try:
            return ctx.library_tasks.sync_nfo(options).as_dict()
        except TaskBusyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    def search_index(progress: Progress) -> str:
        with ctx.engine.begin() as conn:
            if not is_sqlite(conn):
                return "Nur für SQLite nötig"
            rebuild(conn)
        return "Neu aufgebaut"

    def artwork(progress: Progress) -> str:
        updated = 0
        with ctx.sessions() as db:
            channels = list(db.scalars(select(Channel).where(Channel.youtube_id.startswith("UC"))))
            progress.total(len(channels))
            for channel in channels:
                try:
                    source = ctx.catalog.resolve(
                        SubscriptionKind.CHANNEL, channel_url(channel.youtube_id)
                    )
                    store_channel_art(db, ctx.catalog, ctx.settings.media_dir, channel, source)
                    updated += 1
                except Exception as exc:
                    log.info("Kanalbilder für %s: %s", channel.name, exc)
                channel.artwork_checked_at = datetime.now(UTC)
                db.commit()
                progress.step(channel.name)
        ctx.events.publish("channels.updated")
        return f"{updated} Kanäle aktualisiert"

    def verify(progress: Progress) -> str:
        missing = found = 0
        with ctx.sessions() as db:
            videos = list(
                db.scalars(
                    select(Video).where(Video.status.in_([VideoStatus.READY, VideoStatus.MISSING]))
                )
            )
            progress.total(len(videos))
            for video in videos:
                exists = video_file_exists(ctx.settings.media_dir, video)
                if video.status is VideoStatus.READY and not exists:
                    video.status = VideoStatus.MISSING
                    missing += 1
                elif video.status is VideoStatus.MISSING and exists:
                    video.status = VideoStatus.READY
                    found += 1
                progress.step(video.title)
            db.commit()
        if missing or found:
            ctx.events.publish("video.updated", video={})
        parts = [f"{len(videos)} Videos geprüft"]
        if missing:
            parts.append(f"{missing} Dateien fehlen")
        if found:
            parts.append(f"{found} wieder da")
        return ", ".join(parts)

    def cache(progress: Progress) -> str:
        freed = ctx.transcoder.cleanup_cache(limit=0)
        return f"{freed / 1024**2:.0f} MB freigegeben"

    work = {"search-index": search_index, "artwork": artwork, "verify": verify, "cache": cache}
    try:
        return ctx.library_tasks.run(action, LABELS[action], work[action]).as_dict()
    except TaskBusyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
