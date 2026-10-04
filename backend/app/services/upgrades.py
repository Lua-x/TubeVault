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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ACTIVE_JOB_STATUSES, DownloadJob, SubscriptionItem, Video, VideoStatus
from app.models.video import LOCAL_PREFIX
from app.services.app_settings import DownloadOptions, load_app_settings
from app.services.connectivity import Connectivity
from app.services.downloader import Downloader
from app.services.videos import video_file_exists

log = logging.getLogger(__name__)

UPGRADE_KEY = "upgrade"
WINDOW = timedelta(days=7)
MIN_AGE = timedelta(hours=1)
RECHECK = timedelta(hours=12)
PER_ROUND = 3
DEFAULT_TARGET = 1080  # "best quality": anything above 1080p only on request


def utcnow() -> datetime:
    return datetime.now(UTC)


def best_height(info: dict[str, Any], max_height: int | None) -> int | None:
    """Highest video resolution YouTube offers now, within the limit."""
    heights = [
        fmt["height"]
        for fmt in info.get("formats") or []
        if isinstance(fmt.get("height"), int) and fmt.get("vcodec") not in (None, "none")
    ]
    if max_height:
        heights = [height for height in heights if height <= max_height]
    return max(heights, default=None)


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
            candidates: list[tuple[Video, DownloadOptions]] = []
            for video in recent:
                if now - self._checked.get(video.id, datetime.min.replace(tzinfo=UTC)) < RECHECK:
                    continue
                options = DownloadOptions.model_validate(
                    settings.downloads.model_dump() | subscription_options(db, video)
                )
                target = options.max_height or DEFAULT_TARGET
                if video.height is not None and video.height < target:
                    candidates.append((video, options))
            queued: list[int] = []
            for video, options in candidates[:PER_ROUND]:
                self._checked[video.id] = now
                if has_active_job(db, video) or not video_file_exists(self._media_dir, video):
                    continue
                try:
                    meta = self._downloader.fetch_metadata(watch_url(video))
                except Exception as exc:
                    log.info("Qualität von %s nicht prüfbar: %s", video.youtube_id, exc)
                    continue
                best = best_height(meta.raw, options.max_height)
                if best is not None and video.height is not None and best > video.height:
                    log.info(
                        "Bessere Qualität für „%s“: %sp statt %sp", video.title, best, video.height
                    )
                    queued.append(queue_upgrade(db, video).id)
        if queued and self.on_queued:
            self.on_queued(queued)
        return queued
