from __future__ import annotations

from pydantic import BaseModel


class DiskUsage(BaseModel):
    total: int
    used: int
    free: int


class SystemInfo(BaseModel):
    version: str
    ytdlp_version: str | None
    ffmpeg_version: str | None
    media_dir: str
    disk: DiskUsage | None
    video_count: int
    library_size: int
