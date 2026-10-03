"""Health check and system information."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app import __version__
from app.core.deps import AdminUser, AppConfig, Context, CurrentUser, DbSession
from app.models import Video, VideoStatus
from app.schemas.system import DiskUsage, SystemInfo
from app.services.access import visible_videos
from app.services.ytdlp_updater import current_ytdlp_version

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@lru_cache(maxsize=1)
def ffmpeg_version() -> str | None:
    binary = shutil.which("ffmpeg")
    if binary is None:
        return None
    try:
        output = subprocess.run(  # noqa: S603 – fixed arguments
            [binary, "-version"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    first = output.splitlines()[0] if output else ""
    parts = first.split()
    return parts[2] if len(parts) > 2 and parts[0] == "ffmpeg" else first or None


@router.get("/system/info")
def system_info(user: CurrentUser, db: DbSession, settings: AppConfig) -> SystemInfo:
    disk: DiskUsage | None = None
    try:
        usage = shutil.disk_usage(settings.media_dir)
        disk = DiskUsage(total=usage.total, used=usage.used, free=usage.free)
    except OSError:
        pass
    ready = visible_videos(select(Video), user).where(Video.status == VideoStatus.READY).subquery()
    return SystemInfo(
        version=__version__,
        ytdlp_version=current_ytdlp_version(),
        ffmpeg_version=ffmpeg_version(),
        media_dir=str(settings.media_dir),
        disk=disk,
        video_count=db.scalar(select(func.count()).select_from(ready)) or 0,
        library_size=db.scalar(select(func.coalesce(func.sum(ready.c.filesize), 0))) or 0,
    )


@router.get("/library/task")
def library_task(_: AdminUser, ctx: Context) -> dict[str, object] | None:
    """The running (or last) library task, e.g. moving files or writing NFOs."""
    state = ctx.library_tasks.current
    return state.as_dict() if state else None
