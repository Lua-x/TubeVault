"""Subscriptions: filters, checking for new videos and cleaning up old ones."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.errors import classify_error, clean_message, retry_delay
from app.core.events import EventBus
from app.models import (
    ACTIVE_JOB_STATUSES,
    Channel,
    DownloadJob,
    ErrorKind,
    ItemState,
    Subscription,
    SubscriptionItem,
    SubscriptionKind,
    Video,
    VideoStatus,
)
from app.services.catalog import Catalog, Entry, SourceInfo
from app.services.downloader import VideoMetadata
from app.services.library import relative_to_media, resolve_media_path
from app.services.videos import delete_video_files, get_or_create_channel, video_file_exists

log = logging.getLogger(__name__)

CHECK_DEPTH = 50  # newest entries per channel tab looked at in a regular check
PLAYLIST_LIMIT = 2000
# Channel listings only know dates like "3 weeks ago"; the exact check happens later.
APPROXIMATE_DATE_MARGIN = timedelta(days=7)
IMAGE_REFRESH = timedelta(days=7)
FFMPEG = shutil.which("ffmpeg")
SKIPPED_ON_SUBSCRIBE = "Älter – beim Abonnieren übersprungen"


def utcnow() -> datetime:
    return datetime.now(UTC)


def _minutes(seconds: int) -> str:
    minutes = seconds / 60
    return f"{minutes:g} min" if minutes < 60 else f"{minutes / 60:g} h"


# --- filters --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FilterRules:
    include_shorts: bool
    include_live: bool
    min_duration_s: int | None
    max_duration_s: int | None
    cutoff: date | None

    @classmethod
    def of(cls, sub: Subscription, today: date | None = None) -> FilterRules:
        today = today or utcnow().date()
        cutoffs = [d for d in (sub.date_after,) if d]
        if sub.keep_days:
            cutoffs.append(today - timedelta(days=sub.keep_days))
        return cls(
            include_shorts=sub.include_shorts,
            include_live=sub.include_live,
            min_duration_s=sub.min_duration_s,
            max_duration_s=sub.max_duration_s,
            cutoff=max(cutoffs) if cutoffs else None,
        )

    def reason(
        self,
        *,
        is_short: bool,
        was_live: bool,
        duration_s: int | None,
        upload_date: date | None,
        approximate: bool = False,
    ) -> str | None:
        if is_short and not self.include_shorts:
            return "Shorts ausgeschlossen"
        if was_live and not self.include_live:
            return "Livestream ausgeschlossen"
        if duration_s is not None:
            if self.min_duration_s and duration_s < self.min_duration_s:
                return f"Kürzer als {_minutes(self.min_duration_s)}"
            if self.max_duration_s and duration_s > self.max_duration_s:
                return f"Länger als {_minutes(self.max_duration_s)}"
        if upload_date and self.cutoff:
            margin = APPROXIMATE_DATE_MARGIN if approximate else timedelta(0)
            if upload_date + margin < self.cutoff:
                return f"Vor dem {self.cutoff.strftime('%d.%m.%Y')} hochgeladen"
        return None

    def entry_reason(self, entry: Entry) -> str | None:
        if entry.unavailable:
            return "Nicht verfügbar"
        return self.reason(
            is_short=entry.is_short,
            was_live=entry.live_status == "was_live",
            duration_s=entry.duration_s,
            upload_date=entry.upload_date,
            approximate=True,
        )

    def metadata_reason(self, meta: VideoMetadata) -> str | None:
        return self.reason(
            is_short=meta.is_short,
            was_live=meta.was_live,
            duration_s=meta.duration_s,
            upload_date=meta.upload_date,
        )


# --- channel artwork ------------------------------------------------------------


def _to_jpeg(data: bytes) -> bytes | None:
    if data[:3] == b"\xff\xd8\xff":
        return data
    if FFMPEG is None:
        return None
    command = [FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-f", "image2", "-c:v", "mjpeg"]
    command += ["-q:v", "2", "pipe:1"]
    try:
        result = subprocess.run(  # noqa: S603 – fixed arguments, absolute path
            command, input=data, capture_output=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout or None


def store_channel_art(
    db: Session, catalog: Catalog, media_dir: Path, channel: Channel, source: SourceInfo
) -> None:
    """Avatar as `folder.jpg` and banner as `banner.jpg` – both picked up by Jellyfin too."""
    for kind, url, filename in (
        ("avatar", source.avatar_url, "folder.jpg"),
        ("banner", source.banner_url, "banner.jpg"),
    ):
        if not url:
            continue
        target = media_dir / channel.folder_name / filename
        current = getattr(channel, f"{kind}_path")
        if current and target.exists():
            age = utcnow() - datetime.fromtimestamp(target.stat().st_mtime, UTC)
            if age < IMAGE_REFRESH:
                continue
        data = catalog.fetch_image(url)
        jpeg = _to_jpeg(data) if data else None
        if not jpeg:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        tmp.write_bytes(jpeg)
        tmp.replace(target)
        setattr(channel, f"{kind}_path", relative_to_media(media_dir, target))
        channel.updated_at = utcnow()


# --- checking ---------------------------------------------------------------------


@dataclass(slots=True)
class CheckResult:
    queued: int = 0
    filtered: int = 0
    skipped: int = 0
    linked: int = 0


class SubscriptionChecker:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        events: EventBus,
        catalog: Catalog,
        on_jobs_created: Any = None,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._events = events
        self._catalog = catalog
        self._on_jobs_created = on_jobs_created
        self._lock = threading.Lock()
        self._running: set[int] = set()

    def is_checking(self, subscription_id: int) -> bool:
        with self._lock:
            return subscription_id in self._running

    def check(self, subscription_id: int) -> CheckResult | None:
        with self._lock:
            if subscription_id in self._running:
                return None
            self._running.add(subscription_id)
        self._events.publish("subscription.updated", subscription_id=subscription_id)
        try:
            return self._check(subscription_id)
        except Exception as exc:
            self._record_error(subscription_id, exc)
            return None
        finally:
            with self._lock:
                self._running.discard(subscription_id)
            self._events.publish("subscription.updated", subscription_id=subscription_id)

    def _record_error(self, subscription_id: int, exc: Exception) -> None:
        kind = classify_error(exc)
        message = clean_message(exc)
        log.warning("Abo %s konnte nicht geprüft werden (%s): %s", subscription_id, kind, message)
        with self._sessions() as db:
            sub = db.get(Subscription, subscription_id)
            if sub is None:
                return
            delay = timedelta(minutes=min(sub.check_interval_minutes, 60))
            if kind is ErrorKind.RATE_LIMITED:
                delay = max(delay, retry_delay(kind, 1))
            sub.last_check_error = message
            sub.next_check_at = utcnow() + delay
            db.commit()

    def _check(self, subscription_id: int) -> CheckResult:
        with self._sessions() as db:
            sub = db.get(Subscription, subscription_id)
            if sub is None:
                return CheckResult()
            kind, url, first = sub.kind, sub.url, sub.last_checked_at is None
            tabs = ["videos"]
            if sub.include_shorts:
                tabs.append("shorts")
            if sub.include_live:
                tabs.append("streams")
            if kind is SubscriptionKind.PLAYLIST:
                limit: int | None = PLAYLIST_LIMIT
            elif first and sub.backfill is None:
                limit = None  # "all videos" was chosen
            else:
                limit = max(CHECK_DEPTH, sub.backfill or 0)

        listing = self._catalog.list_entries(kind, url, tabs=tabs, limit=limit)

        with self._sessions() as db:
            sub = db.get(Subscription, subscription_id)
            if sub is None:
                return CheckResult()
            result, new_jobs = self._apply(db, sub, listing.entries, first)
            self._update_source(db, sub, listing.source)
            now = utcnow()
            sub.last_checked_at = now
            sub.next_check_at = now + timedelta(minutes=sub.check_interval_minutes)
            sub.last_check_error = None
            db.commit()
            log.info(
                "Abo „%s“ geprüft: %d neu, %d gefiltert, %d übersprungen",
                sub.title, result.queued, result.filtered, result.skipped,
            )  # fmt: skip
            job_ids = [job.id for job in new_jobs]

        if job_ids and self._on_jobs_created:
            self._on_jobs_created(job_ids)
        return result

    def _apply(
        self, db: Session, sub: Subscription, entries: list[Entry], first: bool
    ) -> tuple[CheckResult, list[DownloadJob]]:
        known = set(
            db.scalars(
                select(SubscriptionItem.youtube_id).where(
                    SubscriptionItem.subscription_id == sub.id
                )
            )
        )
        rules = FilterRules.of(sub)
        result = CheckResult()
        candidates: list[Entry] = []
        seen: set[str] = set()
        for entry in entries:
            if entry.youtube_id in known or entry.youtube_id in seen:
                continue
            seen.add(entry.youtube_id)
            if entry.live_status in ("is_live", "is_upcoming"):
                continue  # not downloadable yet – picked up by a later check
            reason = rules.entry_reason(entry)
            if reason:
                self._add_item(db, sub, entry, ItemState.FILTERED, reason)
                result.filtered += 1
            else:
                candidates.append(entry)

        limit = None
        if first and sub.backfill is not None:
            limit = sub.backfill
        if sub.keep_last:
            limit = min(limit, sub.keep_last) if limit is not None else sub.keep_last
        take = candidates if limit is None else candidates[:limit]
        for entry in candidates[len(take) :]:
            self._add_item(
                db, sub, entry, ItemState.SKIPPED, "Älter – beim Abonnieren übersprungen"
            )
            result.skipped += 1

        new_jobs: list[DownloadJob] = []
        for entry in reversed(take):  # oldest first, so the queue follows the upload order
            job = self._queue(db, sub, entry, result)
            if job is not None:
                new_jobs.append(job)
        db.flush()
        return result, new_jobs

    def _add_item(
        self,
        db: Session,
        sub: Subscription,
        entry: Entry,
        state: ItemState,
        reason: str | None = None,
        *,
        video_id: int | None = None,
        job_id: int | None = None,
    ) -> SubscriptionItem:
        item = SubscriptionItem(
            subscription_id=sub.id,
            youtube_id=entry.youtube_id,
            title=entry.title,
            upload_date=entry.upload_date,
            duration_s=entry.duration_s,
            state=state,
            reason=reason,
            video_id=video_id,
            job_id=job_id,
        )
        db.add(item)
        return item

    def _queue(
        self, db: Session, sub: Subscription, entry: Entry, result: CheckResult
    ) -> DownloadJob | None:
        video = db.scalar(select(Video).where(Video.youtube_id == entry.youtube_id))
        if (
            video is not None
            and video.status is VideoStatus.READY
            and video_file_exists(self._settings.media_dir, video)
        ):
            self._add_item(db, sub, entry, ItemState.DOWNLOADED, video_id=video.id)
            result.linked += 1
            return None
        active = db.scalar(
            select(DownloadJob).where(
                DownloadJob.youtube_id == entry.youtube_id,
                DownloadJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
        if active is not None:
            self._add_item(db, sub, entry, ItemState.QUEUED, job_id=active.id)
            result.linked += 1
            return None
        job = DownloadJob(
            url=f"https://www.youtube.com/watch?v={entry.youtube_id}",
            youtube_id=entry.youtube_id,
            video_id=video.id if video else None,
            options=dict(sub.download_options or {}),
            subscription_id=sub.id,
            requested_by_id=sub.created_by_id,
            priority=0,
        )
        db.add(job)
        db.flush()
        self._add_item(db, sub, entry, ItemState.QUEUED, job_id=job.id)
        result.queued += 1
        return job

    def _update_source(self, db: Session, sub: Subscription, source: SourceInfo) -> None:
        sub.title = source.title or sub.title
        if not source.channel_id:
            return
        channel = get_or_create_channel(
            db,
            VideoMetadata(
                youtube_id="",
                title="",
                webpage_url="",
                channel_id=source.channel_id,
                channel_name=source.channel_name or source.title,
                channel_handle=source.channel_handle,
                channel_url=source.channel_url,
            ),
        )
        sub.channel_id = channel.id
        if sub.kind is SubscriptionKind.CHANNEL:
            try:
                store_channel_art(db, self._catalog, self._settings.media_dir, channel, source)
            except OSError as exc:
                log.warning("Kanalbilder für %s nicht gespeichert: %s", channel.name, exc)


# --- items after a download -----------------------------------------------------------


def update_items_for_job(
    db: Session,
    job_id: int,
    state: ItemState,
    *,
    reason: str | None = None,
    video_id: int | None = None,
) -> None:
    for item in db.scalars(select(SubscriptionItem).where(SubscriptionItem.job_id == job_id)):
        item.state = state
        item.reason = reason
        if video_id is not None:
            item.video_id = video_id


def mark_video_removed(db: Session, video_id: int, reason: str) -> None:
    for item in db.scalars(select(SubscriptionItem).where(SubscriptionItem.video_id == video_id)):
        item.state = ItemState.REMOVED
        item.reason = reason


# --- cleanup ----------------------------------------------------------------------------


def _video_date(video: Video) -> date | None:
    if video.upload_date:
        return video.upload_date
    return video.downloaded_at.date() if video.downloaded_at else None


def cleanup_candidates(db: Session, sub: Subscription, today: date) -> set[int]:
    """Videos the subscription would delete under its own rules."""
    if not sub.has_cleanup:
        return set()
    videos = list(
        db.scalars(
            select(Video)
            .join(SubscriptionItem, SubscriptionItem.video_id == Video.id)
            .where(
                SubscriptionItem.subscription_id == sub.id,
                SubscriptionItem.state == ItemState.DOWNLOADED,
                Video.status == VideoStatus.READY,
            )
        )
    )
    videos.sort(key=lambda v: (_video_date(v) or date.min, v.id), reverse=True)
    doomed: set[int] = set()
    if sub.keep_last:
        doomed |= {v.id for v in videos[sub.keep_last :]}
    if sub.keep_days:
        cutoff = today - timedelta(days=sub.keep_days)
        doomed |= {v.id for v in videos if (d := _video_date(v)) is not None and d < cutoff}
    return doomed


def run_cleanup(db: Session, media_dir: Path, today: date | None = None) -> list[int]:
    """Delete videos every linked subscription agrees to drop. Manual videos are kept."""
    today = today or utcnow().date()
    subs = list(db.scalars(select(Subscription)))
    doomed_by_sub = {sub.id: cleanup_candidates(db, sub, today) for sub in subs}
    candidates = set().union(*doomed_by_sub.values()) if doomed_by_sub else set()
    deleted: list[int] = []
    for video_id in sorted(candidates):
        video = db.get(Video, video_id)
        if video is None or video.manual:
            continue
        linked = set(
            db.scalars(
                select(SubscriptionItem.subscription_id).where(
                    SubscriptionItem.video_id == video_id,
                    SubscriptionItem.state == ItemState.DOWNLOADED,
                )
            )
        )
        if not all(video_id in doomed_by_sub.get(sub_id, set()) for sub_id in linked):
            continue
        delete_video_files(media_dir, video)
        mark_video_removed(db, video_id, "Automatisch aufgeräumt")
        db.delete(video)
        deleted.append(video_id)
    if deleted:
        db.commit()
        log.info("Aufräumen: %d Videos gelöscht", len(deleted))
    return deleted


def delete_subscription(
    db: Session, media_dir: Path, sub: Subscription, *, delete_videos: bool
) -> list[int]:
    """Remove a subscription; optionally delete videos no one else keeps."""
    deleted: list[int] = []
    if delete_videos:
        video_ids = {
            video_id
            for video_id in db.scalars(
                select(SubscriptionItem.video_id).where(SubscriptionItem.subscription_id == sub.id)
            )
            if video_id is not None
        }
        for video_id in video_ids:
            video = db.get(Video, video_id)
            if video is None or video.manual:
                continue
            others = db.scalar(
                select(SubscriptionItem.id).where(
                    SubscriptionItem.video_id == video_id,
                    SubscriptionItem.subscription_id != sub.id,
                    SubscriptionItem.state == ItemState.DOWNLOADED,
                )
            )
            if others is not None:
                continue
            delete_video_files(media_dir, video)
            db.delete(video)
            deleted.append(video_id)
    db.delete(sub)
    db.commit()
    return deleted


def subscription_stats(db: Session, sub_ids: list[int]) -> dict[int, dict[str, int]]:
    stats = {sub_id: {state.value: 0 for state in ItemState} for sub_id in sub_ids}
    if not sub_ids:
        return stats
    rows = db.execute(
        select(SubscriptionItem.subscription_id, SubscriptionItem.state, func.count())
        .where(SubscriptionItem.subscription_id.in_(sub_ids))
        .group_by(SubscriptionItem.subscription_id, SubscriptionItem.state)
    )
    for sub_id, state, count in rows:
        stats[sub_id][ItemState(state).value] = int(count)
    return stats


def channel_media_path(media_dir: Path, channel: Channel | None, kind: str) -> Path | None:
    if channel is None:
        return None
    relative = channel.avatar_path if kind == "avatar" else channel.banner_path
    if not relative:
        return None
    try:
        path = resolve_media_path(media_dir, relative)
    except ValueError:
        return None
    return path if path.is_file() else None


ARTWORK_RETRY = timedelta(days=7)


def refresh_channel_artwork(db: Session, catalog: Catalog, media_dir: Path, limit: int = 5) -> int:
    """Fetch avatar and banner for channels that have none yet (e.g. only hand-added videos)."""
    cutoff = utcnow() - ARTWORK_RETRY
    channels = list(
        db.scalars(
            select(Channel)
            .where(
                Channel.avatar_path.is_(None),
                Channel.youtube_id.startswith("UC"),
                (Channel.artwork_checked_at.is_(None)) | (Channel.artwork_checked_at < cutoff),
            )
            .limit(limit)
        )
    )
    updated = 0
    for channel in channels:
        channel.artwork_checked_at = utcnow()
        try:
            source = catalog.resolve(SubscriptionKind.CHANNEL, channel_url_for(channel.youtube_id))
            store_channel_art(db, catalog, media_dir, channel, source)
            updated += int(channel.avatar_path is not None)
        except Exception as exc:
            log.debug("Kanalbilder für %s nicht geladen: %s", channel.name, exc)
        db.commit()
    return updated


def channel_url_for(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}"
