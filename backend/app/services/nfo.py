""".nfo files for Jellyfin, Emby and Kodi (Plex reads the folder layout and images).

Every file we write carries a marker comment, so switching NFOs off only removes our own.
"""

from __future__ import annotations

import logging
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import UTC
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, Video, VideoStatus
from app.services.library import UnsafePathError, nfo_path, resolve_media_path

log = logging.getLogger(__name__)

MARKER = "Erstellt von TubeVault"


def _element(parent: ET.Element, tag: str, text: object | None, **attrs: str) -> None:
    if text is None or text == "":
        return
    child = ET.SubElement(parent, tag, attrs)
    child.text = str(text)


def _serialize(root: ET.Element) -> str:
    root.insert(0, ET.Comment(f" {MARKER} "))
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n{body}\n'


def _id_type(item: Video | Channel) -> str:
    """Own videos have no YouTube ID – Jellyfin must not look them up there."""
    return "tubevault" if item.is_local else "youtube"


def _common(root: ET.Element, video: Video) -> None:
    _element(root, "title", video.title)
    _element(root, "plot", video.description)
    if video.duration_s:
        _element(root, "runtime", max(1, round(video.duration_s / 60)))
    if video.channel:
        _element(root, "studio", video.channel.name)
    _element(root, "uniqueid", video.youtube_id, type=_id_type(video), default="true")
    added = video.downloaded_at or video.added_at
    if added:
        _element(root, "dateadded", added.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"))


def episode_nfo(video: Video, episode: int) -> str:
    """Season = upload year, episode = MMDD plus a two-digit counter for that day."""
    root = ET.Element("episodedetails")
    _common(root, video)
    if video.channel:
        _element(root, "showtitle", video.channel.name)
    if video.upload_date:
        _element(root, "season", video.upload_date.year)
        _element(root, "episode", episode)
        _element(root, "aired", video.upload_date.isoformat())
    return _serialize(root)


def movie_nfo(video: Video) -> str:
    root = ET.Element("movie")
    _common(root, video)
    if video.upload_date:
        _element(root, "premiered", video.upload_date.isoformat())
        _element(root, "year", video.upload_date.year)
    if video.channel:
        _element(root, "director", video.channel.name)
    _element(root, "tag", "YouTube")
    return _serialize(root)


def tvshow_nfo(channel: Channel) -> str:
    root = ET.Element("tvshow")
    _element(root, "title", channel.name)
    _element(root, "plot", channel.description)
    _element(root, "studio", "TubeVault" if channel.is_local else "YouTube")
    _element(root, "uniqueid", channel.youtube_id, type=_id_type(channel), default="true")
    return _serialize(root)


def is_ours(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return MARKER.encode() in handle.read(512)
    except OSError:
        return False


def _write(path: Path, content: str) -> None:
    """Atomic write that leaves files from other tools alone."""
    if path.exists() and not is_ours(path):
        return
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def episode_number(db: Session, video: Video) -> int:
    """MMDD01, MMDD02, … in the order the videos of that day were published (by ID)."""
    if not video.upload_date:
        return 0
    same_day = db.scalars(
        select(Video.youtube_id)
        .where(Video.channel_id == video.channel_id, Video.upload_date == video.upload_date)
        .order_by(Video.youtube_id)
    ).all()
    index = same_day.index(video.youtube_id) + 1 if video.youtube_id in same_day else 1
    return int(f"{video.upload_date.month:02d}{video.upload_date.day:02d}{min(index, 99):02d}")


def _video_file(media_dir: Path, video: Video) -> Path | None:
    if not video.file_path:
        return None
    try:
        return resolve_media_path(media_dir, video.file_path)
    except UnsafePathError:
        return None


def write_video_nfo(db: Session, media_dir: Path, video: Video, layout: str) -> None:
    file = _video_file(media_dir, video)
    if file is None or not file.is_file():
        return
    if layout == "series":
        _write(nfo_path(file), episode_nfo(video, episode_number(db, video)))
        if video.channel:
            write_channel_files(media_dir, video.channel)
    else:
        _write(nfo_path(file), movie_nfo(video))


def write_channel_files(media_dir: Path, channel: Channel) -> None:
    """tvshow.nfo and fanart.jpg (the banner as backdrop) in the channel folder."""
    folder = media_dir / channel.folder_name
    if not folder.is_dir():
        return
    _write(folder / "tvshow.nfo", tvshow_nfo(channel))
    fanart = folder / "fanart.jpg"
    if channel.banner_path and not fanart.exists():
        try:
            shutil.copyfile(resolve_media_path(media_dir, channel.banner_path), fanart)
        except (OSError, UnsafePathError):
            log.debug("Kein fanart.jpg für %s", channel.name)


def write_day_siblings(db: Session, media_dir: Path, video: Video, layout: str) -> None:
    """A new video can shift the episode numbers of others from the same day."""
    if layout != "series" or not video.upload_date:
        write_video_nfo(db, media_dir, video, layout)
        return
    siblings = db.scalars(
        select(Video).where(
            Video.channel_id == video.channel_id,
            Video.upload_date == video.upload_date,
            Video.status == VideoStatus.READY,
        )
    ).all()
    for sibling in siblings:
        write_video_nfo(db, media_dir, sibling, layout)


def remove_video_nfo(media_dir: Path, video: Video) -> None:
    file = _video_file(media_dir, video)
    if file is not None:
        nfo = nfo_path(file)
        if is_ours(nfo):
            nfo.unlink(missing_ok=True)


def remove_channel_files(media_dir: Path, channel: Channel) -> None:
    show = media_dir / channel.folder_name / "tvshow.nfo"
    if is_ours(show):
        show.unlink(missing_ok=True)
