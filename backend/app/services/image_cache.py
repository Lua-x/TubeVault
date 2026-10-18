"""Small copies of thumbnails and channel art in /config – like Jellyfin's image cache.

Browsing the library needs dozens of pictures; read from /media they wake the disks with the
videos every time. The copies live on /config (usually an SSD), named after what the database
knows (path and download time), so serving one never touches /media. The disks spin up when
someone watches – or once, to make a copy that is missing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Channel, Video, VideoStatus, WatchProgress
from app.services.library import UnsafePathError, resolve_media_path

log = logging.getLogger(__name__)

Size = Literal["small", "large", "avatar", "banner"]
# Longest side that matters: cards are ~320 px wide (×2 for sharp screens), the hero and the
# player poster up to ~1280, avatars at most ~128.
WIDTHS: dict[Size, int] = {"small": 640, "large": 1280, "avatar": 256, "banner": 1600}
QUALITY = 82
# The start page shows a video big: one being watched, else the newest. Their large copy is
# made ahead of time too.
RECENT = timedelta(days=3)
WATCHING = timedelta(days=60)


@dataclass(frozen=True)
class CachedImage:
    """A picture in /media and the version the database knows of it."""

    kind: Literal["video", "avatar", "banner"]
    owner: int
    relative: str
    version: str

    @property
    def digest(self) -> str:
        return hashlib.sha1(f"{self.relative}\0{self.version}".encode()).hexdigest()[:12]  # noqa: S324 – a name, not security

    def name(self, size: Size) -> str:
        return f"{self.kind}-{self.owner}-{size}-{self.digest}.jpg"


def _stamp(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def video_image(video: Video) -> CachedImage | None:
    return _video_image(video.id, video.thumbnail_path, video.downloaded_at or video.added_at)


def _video_image(video_id: int, thumbnail: str | None, when: datetime | None) -> CachedImage | None:
    if not thumbnail:
        return None
    # A new download (or a better version) changes the time; a new layout changes the path.
    return CachedImage("video", video_id, thumbnail, _stamp(when))


def channel_image(channel: Channel | None, kind: Literal["avatar", "banner"]) -> CachedImage | None:
    if channel is None:
        return None
    relative = channel.avatar_path if kind == "avatar" else channel.banner_path
    if not relative:
        return None
    return CachedImage(kind, channel.id, relative, _stamp(channel.updated_at))


class ImageCache:
    def __init__(self, directory: Path, media_dir: Path) -> None:
        self._dir = directory
        self._media_dir = media_dir
        # Pictures that can't be shrunk (broken, unknown format): served as they are, and not
        # tried again until the next start.
        self._failed: set[str] = set()

    @property
    def directory(self) -> Path:
        return self._dir

    def cached(self, image: CachedImage, size: Size) -> Path | None:
        path = self._dir / image.name(size)
        return path if path.is_file() else None

    def gave_up(self, image: CachedImage, size: Size) -> bool:
        return image.name(size) in self._failed

    def get(self, image: CachedImage, size: Size) -> tuple[Path, bool]:
        """The copy, made from the original first if it is missing: (path, is_copy).

        Falls back to the original when no copy can be made. FileNotFoundError when the
        original is gone too.
        """
        name = image.name(size)
        target = self._dir / name
        if target.is_file():
            return target, True
        try:
            source = resolve_media_path(self._media_dir, image.relative)
        except UnsafePathError as exc:
            raise FileNotFoundError(image.relative) from exc
        if not source.is_file():
            self._failed.add(name)
            raise FileNotFoundError(image.relative)
        if name not in self._failed:
            try:
                self._render(source, target, WIDTHS[size])
                return target, True
            except (OSError, ValueError, PILImage.DecompressionBombError) as exc:
                log.info("Kein verkleinertes Bild für %s: %s", image.relative, exc)
                self._failed.add(name)
        return source, False

    def _render(self, source: Path, target: Path, width: int) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        part = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.part")
        try:
            with PILImage.open(source) as original:
                original.draft("RGB", (width, width))  # JPEGs decode at a smaller scale: faster
                picture = original.convert("RGB") if original.mode != "RGB" else original
                picture.thumbnail((width, width * 2))  # never enlarges
                picture.save(part, "JPEG", quality=QUALITY, optimize=True, progressive=True)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)

    def prune(self, keep: set[tuple[str, int, str]]) -> int:
        """Removes copies of pictures that changed or are gone; returns how many."""
        removed = 0
        if not self._dir.is_dir():
            return 0
        stale_parts = time.time() - 3600
        for path in self._dir.iterdir():
            if path.name.startswith("."):
                if path.stat().st_mtime < stale_parts:  # left behind by a crash
                    path.unlink(missing_ok=True)
                continue
            parts = path.stem.split("-")
            if (
                len(parts) == 4
                and parts[1].isdigit()
                and (parts[0], int(parts[1]), parts[3]) in keep
            ):
                continue
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def size_bytes(self) -> int:
        if not self._dir.is_dir():
            return 0
        return sum(p.stat().st_size for p in self._dir.iterdir() if p.is_file())


class ImageWarmer:
    """Makes the copies ahead of time: once for the whole library (after an update), then for
    what new downloads bring – right after them, while the disks are awake anyway."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        cache: ImageCache,
        *,
        interval: float = 600.0,
        first_delay: float = 20.0,
    ) -> None:
        self._sessions = sessions
        self._cache = cache
        self._interval = interval
        self._first_delay = first_delay
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="image-cache", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        if self._stop.wait(self._first_delay):  # let the start settle first
            return
        while not self._stop.is_set():
            try:
                made = self.run_round()
                if made:
                    log.info("Bilder-Cache: %d verkleinerte Bilder angelegt", made)
            except Exception:
                log.exception("Bilder-Cache konnte nicht aufgefüllt werden")
            self._wake.wait(self._interval)
            self._wake.clear()

    def _wanted(self) -> tuple[list[tuple[CachedImage, Size]], set[tuple[str, int, str]]]:
        now = datetime.now(UTC)
        recent = now - RECENT
        wanted: list[tuple[CachedImage, Size]] = []
        keep: set[tuple[str, int, str]] = set()
        with self._sessions() as db:
            watching = set(
                db.scalars(
                    select(WatchProgress.video_id).where(
                        WatchProgress.watched.is_(False), WatchProgress.updated_at >= now - WATCHING
                    )
                )
            )
            rows = db.execute(
                select(Video.id, Video.thumbnail_path, Video.downloaded_at, Video.added_at).where(
                    Video.status == VideoStatus.READY, Video.thumbnail_path.is_not(None)
                )
            ).all()
            for video_id, thumbnail, downloaded_at, added_at in rows:
                when = downloaded_at or added_at
                image = _video_image(video_id, thumbnail, when)
                if image is None:
                    continue
                keep.add((image.kind, image.owner, image.digest))
                wanted.append((image, "small"))
                new = when is not None and when.replace(tzinfo=when.tzinfo or UTC) >= recent
                if new or video_id in watching:
                    wanted.append((image, "large"))
            for channel in db.scalars(select(Channel)).all():
                for kind in ("avatar", "banner"):
                    art = channel_image(channel, kind)
                    if art is not None:
                        keep.add((art.kind, art.owner, art.digest))
                        wanted.append((art, kind))
        return wanted, keep

    def run_round(self) -> int:
        """Makes the missing copies and drops outdated ones; returns how many were made."""
        wanted, keep = self._wanted()
        made = 0
        for image, size in wanted:
            if self._stop.is_set():
                return made
            if self._cache.cached(image, size) or self._cache.gave_up(image, size):
                continue
            try:
                made += int(self._cache.get(image, size)[1])
            except FileNotFoundError:
                continue  # the original is gone; "Dateien prüfen" takes care of that
        self._cache.prune(keep)
        return made
