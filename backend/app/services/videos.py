"""Creating, updating and deleting videos and their files."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Channel, Video
from app.services.downloader import VideoMetadata
from app.services.library import UnsafePathError, resolve_media_path, sanitize_component

log = logging.getLogger(__name__)

UNKNOWN_CHANNEL_ID = "unknown"


def get_or_create_channel(db: Session, meta: VideoMetadata) -> Channel:
    youtube_id = meta.channel_id or UNKNOWN_CHANNEL_ID
    channel = db.scalar(select(Channel).where(Channel.youtube_id == youtube_id))
    name = meta.channel_name or "Unbekannter Kanal"
    if channel is not None:
        # The folder name stays as it is so existing files keep their location.
        channel.name = name
        channel.handle = meta.channel_handle or channel.handle
        channel.url = meta.channel_url or channel.url
        return channel

    folder = sanitize_component(name, max_bytes=120, fallback="Unknown")
    taken = db.scalar(
        select(func.count())
        .select_from(Channel)
        .where(func.lower(Channel.folder_name) == folder.lower())
    )
    if taken:
        folder = f"{folder} [{youtube_id}]"
    channel = Channel(
        youtube_id=youtube_id,
        name=name,
        handle=meta.channel_handle,
        url=meta.channel_url,
        folder_name=folder,
    )
    db.add(channel)
    db.flush()
    return channel


def upsert_video(db: Session, meta: VideoMetadata, added_by_id: int | None) -> Video:
    channel = get_or_create_channel(db, meta)
    video = db.scalar(select(Video).where(Video.youtube_id == meta.youtube_id))
    if video is None:
        video = Video(youtube_id=meta.youtube_id, title=meta.title, added_by_id=added_by_id)
        db.add(video)
    video.channel_id = channel.id
    video.title = meta.title
    video.description = meta.description
    video.upload_date = meta.upload_date
    video.duration_s = meta.duration_s
    video.view_count = meta.view_count
    video.is_short = meta.is_short
    video.was_live = meta.was_live
    video.chapters = meta.chapters
    video.source_url = meta.webpage_url or None
    db.flush()
    return video


def video_file_exists(media_dir: Path, video: Video) -> bool:
    if not video.file_path:
        return False
    try:
        return resolve_media_path(media_dir, video.file_path).is_file()
    except UnsafePathError:
        return False


def delete_video_files(media_dir: Path, video: Video) -> None:
    """Remove the video, thumbnail and subtitle files, then prune empty folders."""
    paths = [video.file_path, video.thumbnail_path, *(s.file_path for s in video.subtitles)]
    if video.file_path:
        paths.append(Path(video.file_path).with_suffix(".nfo").as_posix())
    parents: set[Path] = set()
    for relative in paths:
        if not relative:
            continue
        try:
            path = resolve_media_path(media_dir, relative)
        except UnsafePathError:
            log.warning("Unsicherer Pfad wird nicht gelöscht: %s", relative)
            continue
        path.unlink(missing_ok=True)
        parents.add(path.parent)

    root = media_dir.resolve()
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        current = parent
        while current != root and current.is_relative_to(root):
            try:
                current.rmdir()  # only succeeds when empty
            except OSError:
                break
            current = current.parent
