"""Fetch the better version of videos that were downloaded in low quality.

Right after an upload YouTube often only offers low resolutions; HD follows minutes to
hours later. For videos below their target quality (the subscription's limit, else
1080p), TubeVault asks YouTube again during the first days – at most twice a day per
video and a few per round – and only downloads again when a better format exists.
The download replaces the file in place (see DownloadManager): same video, same watch
progress, playlists and metadata.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import classify_error
from app.models import (
    ACTIVE_JOB_STATUSES,
    DownloadJob,
    ErrorKind,
    SubscriptionItem,
    Video,
    VideoStatus,
)
from app.models.video import LOCAL_PREFIX
from app.services.app_settings import AppSettings, DownloadOptions, load_app_settings
from app.services.connectivity import Connectivity
from app.services.downloader import Downloader
from app.services.videos import video_file_exists

if TYPE_CHECKING:
    from app.workers.library_tasks import Progress

log = logging.getLogger(__name__)

UPGRADE_KEY = "upgrade"
WINDOW = timedelta(days=7)
MIN_AGE = timedelta(hours=1)
RECHECK = timedelta(hours=12)
PER_ROUND = 3
# "Beste Qualität": up to 4K by itself; 8K only on request ("Neu laden").
BEST_TARGET = 2160


def utcnow() -> datetime:
    return datetime.now(UTC)


def resolution(width: Any, height: Any) -> int | None:
    """The shorter side – what "1080p" means, for portrait videos (Shorts) too."""
    sides = [side for side in (width, height) if isinstance(side, int) and side > 0]
    return min(sides) if sides else None


def best_resolution(info: dict[str, Any], limit: int | None) -> int | None:
    """Highest video resolution YouTube offers now, within the limit."""
    found = [
        resolution(fmt.get("width"), fmt.get("height"))
        for fmt in info.get("formats") or []
        if fmt.get("vcodec") not in (None, "none")
    ]
    values = [value for value in found if value is not None]
    if limit:
        values = [value for value in values if value <= limit]
    return max(values, default=None)


def subscription_options(db: Session, video: Video) -> dict[str, Any]:
    """Download options of the subscription the video came from, if any."""
    item = db.scalar(select(SubscriptionItem).where(SubscriptionItem.video_id == video.id).limit(1))
    if item is None or item.subscription is None:
        return {}
    return dict(item.subscription.download_options or {})


def watch_url(video: Video) -> str:
    return video.source_url or f"https://www.youtube.com/watch?v={video.youtube_id}"


def has_active_job(db: Session, video: Video) -> bool:
    return (
        db.scalar(
            select(DownloadJob.id).where(
                DownloadJob.video_id == video.id, DownloadJob.status.in_(ACTIVE_JOB_STATUSES)
            )
        )
        is not None
    )


def queue_upgrade(db: Session, video: Video, requested_by: int | None = None) -> DownloadJob:
    job = DownloadJob(
        url=watch_url(video),
        youtube_id=video.youtube_id,
        video_id=video.id,
        options={**subscription_options(db, video), UPGRADE_KEY: True},
        requested_by_id=requested_by,
        priority=-1,  # new videos first
    )
    db.add(job)
    db.commit()
    return job


class QualityUpgrades:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        media_dir: Any,
        downloader: Downloader,
        connectivity: Connectivity | None = None,
        on_queued: Callable[[list[int]], None] | None = None,
    ) -> None:
        self._sessions = sessions
        self._media_dir = media_dir
        self._downloader = downloader
        self._connectivity = connectivity
        self.on_queued = on_queued
        self._checked: dict[int, datetime] = {}

    def run_round(self) -> list[int]:
        """Ask YouTube about a few candidates; returns the ids of queued upgrade jobs."""
        if self._connectivity and self._connectivity.should_wait():
            return []
        now = utcnow()
        with self._sessions() as db:
            settings = load_app_settings(db)
            if not settings.automation.upgrade_quality:
                return []
            recent = db.scalars(
                select(Video).where(
                    Video.status == VideoStatus.READY,
                    Video.youtube_id.not_like(f"{LOCAL_PREFIX}%"),  # own videos: not on YouTube
                    Video.height.is_not(None),
                    Video.downloaded_at >= (now - WINDOW).replace(tzinfo=None),
                    Video.downloaded_at <= (now - MIN_AGE).replace(tzinfo=None),
                )
            ).all()
            candidates: list[tuple[Video, int]] = []
            for video in recent:
                if now - self._checked.get(video.id, datetime.min.replace(tzinfo=UTC)) < RECHECK:
                    continue
                target = _below_target(db, settings, video)
                if target is not None:
                    candidates.append((video, target))
            queued: list[int] = []
            for video, target in candidates[:PER_ROUND]:
                self._checked[video.id] = now
                if has_active_job(db, video):
                    continue
                try:
                    meta = self._downloader.fetch_metadata(watch_url(video))
                except Exception as exc:
                    log.info("Qualität von %s nicht prüfbar: %s", video.youtube_id, exc)
                    continue
                if self._upgrade_if_better(db, video, best_resolution(meta.raw, target)):
                    queued.append(queue_upgrade(db, video).id)
        if queued and self.on_queued:
            self.on_queued(queued)
        return queued

    def check_all(self, progress: Progress) -> str:
        """Every video below its target, whenever it came: "Bessere Qualität suchen"."""
        with self._sessions() as db:
            settings = load_app_settings(db)
            videos = db.scalars(
                select(Video)
                .where(
                    Video.status == VideoStatus.READY,
                    Video.youtube_id.not_like(f"{LOCAL_PREFIX}%"),
                    Video.height.is_not(None),
                )
                .order_by(Video.downloaded_at.desc())
            ).all()
            candidates = [
                (video.id, target)
                for video in videos
                if (target := _below_target(db, settings, video)) is not None
            ]
        progress.total(len(candidates))
        queued: list[int] = []
        try:
            for video_id, target in candidates:
                with self._sessions() as db:
                    video = db.get(Video, video_id)
                    if video is None or has_active_job(db, video):
                        progress.step()
                        continue
                    url, title = watch_url(video), video.title
                try:
                    meta = self._downloader.fetch_metadata(url)
                except Exception as exc:
                    if classify_error(exc) is ErrorKind.RATE_LIMITED:
                        raise RuntimeError(
                            f"YouTube bremst gerade – bis hierhin {len(queued)} Videos gefunden. "
                            "Später einfach noch einmal starten."
                        ) from exc
                    log.info("Qualität von %s nicht prüfbar: %s", url, exc)
                    progress.step(title)
                    continue
                with self._sessions() as db:
                    video = db.get(Video, video_id)
                    best = best_resolution(meta.raw, target)
                    if video is not None and self._upgrade_if_better(db, video, best):
                        queued.append(queue_upgrade(db, video).id)
                progress.step(title)
        finally:
            if queued and self.on_queued:
                self.on_queued(queued)
        if not queued:
            return "Alle Videos haben schon die beste Qualität"
        if len(queued) == 1:
            return "1 Video wird in besserer Qualität geladen"
        return f"{len(queued)} Videos werden in besserer Qualität geladen"

    def _upgrade_if_better(self, db: Session, video: Video, best: int | None) -> bool:
        current = resolution(video.width, video.height)
        # Only now look at the disk: asking YouTube needs none, and the disks with the
        # videos may sleep (see services/image_cache.py).
        better = best is not None and current is not None and best > current
        if better and video_file_exists(self._media_dir, video):
            log.info("Bessere Qualität für „%s“: %sp statt %sp", video.title, best, current)
            return True
        return False


def _below_target(db: Session, settings: AppSettings, video: Video) -> int | None:
    """The resolution a video should have (its subscription's limit, else 4K), if it hasn't."""
    options = DownloadOptions.model_validate(
        settings.downloads.model_dump() | subscription_options(db, video)
    )
    target = options.max_height or BEST_TARGET
    current = resolution(video.width, video.height)
    return target if current is not None and current < target else None
