"""Streaming and media files: video (HTTP Range), thumbnails, subtitles, chapters."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.core.deps import AppConfig, CurrentUser, DbSession
from app.models import Subtitle, Video
from app.services.library import UnsafePathError, resolve_media_path

router = APIRouter(prefix="/videos", tags=["media"])

VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}
# Files are named after their content (video ID), so they can be cached for a while.
MEDIA_CACHE = "private, max-age=86400"


def _media_file(media_dir: Path, relative: str | None) -> Path:
    if not relative:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei nicht vorhanden")
    try:
        path = resolve_media_path(media_dir, relative)
    except UnsafePathError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei nicht vorhanden") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei nicht vorhanden")
    return path


def _video(db: DbSession, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video nicht gefunden")
    return video


@router.get("/{video_id}/stream")
def stream_video(video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    """Serves the file with Range support (206 Partial Content), so seeking works."""
    video = _video(db, video_id)
    path = _media_file(settings.media_dir, video.file_path)
    media_type = VIDEO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": MEDIA_CACHE})


@router.get("/{video_id}/download")
def download_video(
    video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig
) -> FileResponse:
    video = _video(db, video_id)
    path = _media_file(settings.media_dir, video.file_path)
    return FileResponse(path, filename=path.name, content_disposition_type="attachment")


@router.get("/{video_id}/thumbnail")
def thumbnail(video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    video = _video(db, video_id)
    path = _media_file(settings.media_dir, video.thumbnail_path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": MEDIA_CACHE})


@router.get("/{video_id}/subtitles/{subtitle_id}.vtt")
def subtitle(
    video_id: int, subtitle_id: int, _: CurrentUser, db: DbSession, settings: AppConfig
) -> FileResponse:
    sub = db.scalar(
        select(Subtitle).where(Subtitle.id == subtitle_id, Subtitle.video_id == video_id)
    )
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Untertitel nicht gefunden")
    path = _media_file(settings.media_dir, sub.file_path)
    return FileResponse(path, media_type="text/vtt; charset=utf-8")


def _vtt_time(seconds: float) -> str:
    millis = round(max(seconds, 0) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def chapters_to_vtt(chapters: list[dict[str, object]], duration: float | None) -> str:
    lines = ["WEBVTT", ""]
    for index, chapter in enumerate(chapters, start=1):
        start = float(chapter.get("start", 0) or 0)  # type: ignore[arg-type]
        end = float(chapter.get("end", 0) or 0)  # type: ignore[arg-type]
        if end <= start:
            end = duration or start + 1
        title = str(chapter.get("title") or f"Kapitel {index}").replace("-->", "→")
        lines += [str(index), f"{_vtt_time(start)} --> {_vtt_time(end)}", title, ""]
    return "\n".join(lines)


@router.get("/{video_id}/chapters.vtt")
def chapters(video_id: int, _: CurrentUser, db: DbSession) -> Response:
    video = _video(db, video_id)
    body = chapters_to_vtt(video.chapters or [], float(video.duration_s or 0) or None)
    return Response(body, media_type="text/vtt; charset=utf-8")
