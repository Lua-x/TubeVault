"""Moving videos between folder layouts (TubeVault ↔ series for media servers)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.models import Video
from app.services.library import (
    UnsafePathError,
    relative_to_media,
    resolve_media_path,
    video_base_path,
)

log = logging.getLogger(__name__)


def target_file(media_dir: Path, video: Video, suffix: str, layout: str) -> Path:
    folder = video.channel.folder_name if video.channel else "Unknown"
    base = video_base_path(folder, video.upload_date, video.title, video.youtube_id, layout)
    return media_dir / base.parent / f"{base.name}{suffix}"


def _renamed(path: Path, old_stem: str, new_file: Path) -> Path:
    """Sidecars follow the video: `<stem>-thumb.jpg` → `<new stem>-thumb.jpg`."""
    name = path.name
    if name.startswith(old_stem):
        name = new_file.stem + name[len(old_stem) :]
    return new_file.parent / name


def prune_empty_dirs(media_dir: Path, folders: set[Path]) -> None:
    root = media_dir.resolve()
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        current = folder
        while current != root and current.is_relative_to(root):
            try:
                current.rmdir()  # only works when empty
            except OSError:
                break
            current = current.parent


def move_video(media_dir: Path, video: Video, layout: str) -> Path | None:
    """Moves the file and its sidecars; updates the paths on `video` (caller commits).

    Returns the old folder when something was moved, so it can be pruned afterwards.
    """
    if not video.file_path:
        return None
    try:
        old_file = resolve_media_path(media_dir, video.file_path)
    except UnsafePathError:
        return None
    if not old_file.is_file():
        return None
    new_file = target_file(media_dir, video, old_file.suffix, layout)
    if new_file.resolve() == old_file:
        return None
    if new_file.exists():
        log.warning("Ziel existiert schon, %s bleibt liegen: %s", video.youtube_id, new_file)
        return None

    old_stem = old_file.stem
    moves: list[tuple[Path, Path]] = [(old_file, new_file)]
    nfo = old_file.with_suffix(".nfo")
    if nfo.is_file():
        moves.append((nfo, new_file.with_suffix(".nfo")))
    thumb_target: Path | None = None
    if video.thumbnail_path:
        try:
            thumb = resolve_media_path(media_dir, video.thumbnail_path)
        except UnsafePathError:
            thumb = None
        if thumb is not None and thumb.is_file():
            thumb_target = _renamed(thumb, old_stem, new_file)
            moves.append((thumb, thumb_target))
    subtitle_targets: list[Path | None] = []
    for sub in video.subtitles:
        try:
            source = resolve_media_path(media_dir, sub.file_path)
        except UnsafePathError:
            subtitle_targets.append(None)
            continue
        if source.is_file():
            target = _renamed(source, old_stem, new_file)
            moves.append((source, target))
            subtitle_targets.append(target)
        else:
            subtitle_targets.append(None)

    new_file.parent.mkdir(parents=True, exist_ok=True)
    done: list[tuple[Path, Path]] = []
    try:
        for source, target in moves:
            os.replace(source, target)
            done.append((source, target))
    except OSError:
        for source, target in reversed(done):  # put everything back
            os.replace(target, source)
        raise

    video.file_path = relative_to_media(media_dir, new_file)
    if thumb_target is not None:
        video.thumbnail_path = relative_to_media(media_dir, thumb_target)
    for sub, sub_target in zip(video.subtitles, subtitle_targets, strict=True):
        if sub_target is not None:
            sub.file_path = relative_to_media(media_dir, sub_target)
    return old_file.parent
