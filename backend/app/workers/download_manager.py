"""Download queue backed by the `download_jobs` table.

A dispatcher thread picks queued jobs and runs them on a thread pool. Jobs survive restarts:
anything that was running when the process stopped is queued again on start.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings
from app.core.errors import classify_error, clean_message, is_retryable, retry_delay
from app.core.events import EventBus
from app.models import (
    ACTIVE_JOB_STATUSES,
    DownloadJob,
    ErrorKind,
    ItemState,
    JobStage,
    JobStatus,
    Subscription,
    Subtitle,
    Video,
    VideoStatus,
)
from app.schemas.jobs import JobOut
from app.schemas.videos import VideoSummary
from app.services import nfo, sponsorblock
from app.services.app_settings import DownloadOptions, load_app_settings, queue_paused
from app.services.connectivity import Connectivity
from app.services.downloader import (
    DownloadCancelledError,
    Downloader,
    DownloadProgress,
    DownloadResult,
    cleanup_temp,
)
from app.services.languages import subtitle_label
from app.services.library import relative_to_media, video_base_path
from app.services.subscriptions import FilterRules, update_items_for_job
from app.services.videos import upsert_video, video_file_exists

log = logging.getLogger(__name__)

MAX_WORKERS = 5
OFFLINE_RETRY = timedelta(minutes=1)
OFFLINE_MESSAGE = (
    "Keine Internetverbindung – der Download startet automatisch, sobald das Netz zurück ist."
)
EVENT_INTERVAL = 0.5
DB_PROGRESS_INTERVAL = 5.0


def utcnow() -> datetime:
    return datetime.now(UTC)


def job_payload(job: DownloadJob) -> dict[str, Any]:
    return JobOut.model_validate(job).model_dump(mode="json")


def video_payload(video: Video) -> dict[str, Any]:
    return VideoSummary.model_validate(video).model_dump(mode="json")


def load_job(db: Session, job_id: int) -> DownloadJob | None:
    return db.scalar(
        select(DownloadJob)
        .where(DownloadJob.id == job_id)
        .options(
            selectinload(DownloadJob.video).selectinload(Video.channel),
            selectinload(DownloadJob.subscription),
        )
    )


class DownloadManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        events: EventBus,
        downloader: Downloader,
        poll_interval: float = 2.0,
        on_download_finished: Callable[[], None] | None = None,
        connectivity: Connectivity | None = None,
    ) -> None:
        self._settings = settings
        self._connectivity = connectivity
        self._sessions = session_factory
        self._events = events
        self._downloader = downloader
        self._poll_interval = poll_interval
        self.on_download_finished = on_download_finished
        self._executor: ThreadPoolExecutor | None = None
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._db_lock = threading.Lock()
        self._running: dict[int, threading.Event] = {}
        # Why a running job was interrupted: "cancel", "pause" or "requeue".
        self._stop_reasons: dict[int, str] = {}

    # --- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        self._recover()
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="download")
        self._thread = threading.Thread(target=self._loop, name="download-dispatcher", daemon=True)
        self._thread.start()
        log.info("Download-Queue gestartet")

    def stop(self, timeout: float = 15.0) -> None:
        self._stop.set()
        self._wake.set()
        with self._lock:
            for cancel in self._running.values():
                cancel.set()
        if self._thread is not None:
            self._thread.join(timeout)
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
        log.info("Download-Queue gestoppt")

    def wake(self) -> None:
        self._wake.set()

    def cancel(self, job_id: int) -> bool:
        """Stop a running job for good. Returns False if the job is not running here."""
        return self._interrupt(job_id, "cancel")

    def pause(self, job_id: int) -> bool:
        """Stop a running job but keep its partial files, so it can resume later."""
        return self._interrupt(job_id, "pause")

    def requeue_running(self) -> int:
        """Put every running job back into the queue (used when the queue is paused)."""
        with self._lock:
            job_ids = list(self._running)
        return sum(self._interrupt(job_id, "requeue") for job_id in job_ids)

    def _interrupt(self, job_id: int, reason: str) -> bool:
        with self._lock:
            event = self._running.get(job_id)
            if event is None:
                return False
            self._stop_reasons[job_id] = reason
        event.set()
        return True

    def is_running(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._running

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._running)

    # --- internals --------------------------------------------------------------

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self._sessions() as db:
            yield db

    def _recover(self) -> None:
        with self._session() as db:
            jobs = db.scalars(select(DownloadJob).where(DownloadJob.status == JobStatus.RUNNING))
            count = 0
            for job in jobs:
                job.status = JobStatus.QUEUED
                job.stage = None
                job.speed = None
                job.eta = None
                count += 1
            db.commit()
            if count:
                log.info("%d unterbrochene Downloads wieder eingereiht", count)
            active = set(
                db.scalars(
                    select(DownloadJob.id).where(DownloadJob.status.in_(ACTIVE_JOB_STATUSES))
                )
            )
        # Partial downloads of jobs that no longer exist.
        temp_root = self._settings.temp_dir
        if temp_root.is_dir():
            for path in temp_root.iterdir():
                name = path.name
                if name.startswith("job-") and name[4:].isdigit() and int(name[4:]) not in active:
                    cleanup_temp(path)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._dispatch()
            except Exception:
                log.exception("Fehler im Download-Dispatcher")
            self._wake.wait(self._poll_interval)
            self._wake.clear()

    def _dispatch(self) -> None:
        if self._executor is None:
            return
        with self._session() as db:
            if queue_paused(db):
                return
            limit = load_app_settings(db).max_concurrent_downloads
            free = limit - self.active_count
            if free <= 0:
                return
            now = utcnow()
            jobs = list(
                db.scalars(
                    select(DownloadJob)
                    .where(
                        DownloadJob.status == JobStatus.QUEUED,
                        or_(
                            DownloadJob.next_attempt_at.is_(None),
                            DownloadJob.next_attempt_at <= now,
                        ),
                    )
                    .order_by(DownloadJob.priority.desc(), DownloadJob.created_at, DownloadJob.id)
                    .limit(free)
                )
            )
            if jobs and self._connectivity and self._connectivity.should_wait():
                return  # offline: the jobs stay queued until the internet is back
            for job in jobs:
                job.status = JobStatus.RUNNING
                job.stage = JobStage.METADATA
                job.attempts += 1
                job.started_at = now
                job.next_attempt_at = None
                job.progress = 0.0
                job.speed = None
                job.eta = None
            db.commit()

            for job in jobs:
                cancel = threading.Event()
                with self._lock:
                    self._running[job.id] = cancel
                fresh = load_job(db, job.id)
                if fresh is not None:
                    self._events.publish("job.updated", job=job_payload(fresh))
                self._executor.submit(self._run, job.id, cancel)

    def _run(self, job_id: int, cancel: threading.Event) -> None:
        try:
            self._process(job_id, cancel)
        except Exception:
            log.exception("Unerwarteter Fehler in Download-Job %s", job_id)
        finally:
            with self._lock:
                self._running.pop(job_id, None)
            self._wake.set()

    def _process(self, job_id: int, cancel: threading.Event) -> None:
        with self._session() as db:
            job = db.get(DownloadJob, job_id)
            if job is None:
                return
            url = job.url
            requested_by = job.requested_by_id
            manual = job.subscription_id is None
            app_settings = load_app_settings(db)
            options = DownloadOptions.model_validate(
                app_settings.downloads.model_dump() | (job.options or {})
            )
            library = app_settings.library
            sub = db.get(Subscription, job.subscription_id) if job.subscription_id else None
            rules = FilterRules.of(sub) if sub else None
        temp_dir = self._settings.temp_dir / f"job-{job_id}"

        try:
            meta = self._downloader.fetch_metadata(url)
            if cancel.is_set():
                raise DownloadCancelledError
            if rules is not None and (reason := rules.metadata_reason(meta)):
                self._skip(job_id, meta.youtube_id, reason)
                return

            with self._db_lock, self._session() as db:
                video = upsert_video(db, meta, requested_by)
                if manual:
                    video.manual = True
                job = db.get(DownloadJob, job_id)
                assert job is not None
                job.video_id = video.id
                job.youtube_id = meta.youtube_id
                if video.status is VideoStatus.READY and video_file_exists(
                    self._settings.media_dir, video
                ):
                    self._finish(db, job, video, note="Bereits in der Bibliothek")
                    return
                video.status = VideoStatus.DOWNLOADING
                job.stage = JobStage.DOWNLOADING
                channel_folder = video.channel.folder_name if video.channel else "Unknown"
                db.commit()
                self._publish_job(db, job_id)

            relative_base = video_base_path(
                channel_folder, meta.upload_date, meta.title, meta.youtube_id, library.layout
            )
            result = self._downloader.download(
                meta,
                media_dir=self._settings.media_dir,
                relative_base=relative_base,
                temp_dir=temp_dir,
                options=options,
                on_progress=self._progress_reporter(job_id),
                is_cancelled=cancel.is_set,
            )
            if cancel.is_set():
                raise DownloadCancelledError

            with self._session() as db:
                job = db.get(DownloadJob, job_id)
                assert job is not None and job.video_id is not None
                stored = db.get(Video, job.video_id)
                assert stored is not None
                self._store_result(db, stored, result)
                if options.sponsorblock_mode == "skip" and options.sponsorblock_categories:
                    sponsorblock.refresh(db, stored, list(options.sponsorblock_categories))
                if library.write_nfo:
                    try:
                        db.flush()
                        nfo.write_day_siblings(db, self._settings.media_dir, stored, library.layout)
                    except OSError:
                        log.warning("NFO für %s fehlt", stored.youtube_id, exc_info=True)
                self._finish(db, job, stored)
            cleanup_temp(temp_dir)

        except DownloadCancelledError:
            self._handle_cancel(job_id, temp_dir)
        except Exception as exc:
            if cancel.is_set():
                self._handle_cancel(job_id, temp_dir)
            else:
                self._handle_error(job_id, exc, temp_dir)

    def _store_result(self, db: Session, video: Video, result: DownloadResult) -> None:
        media_dir = self._settings.media_dir
        video.file_path = relative_to_media(media_dir, result.file_path)
        video.thumbnail_path = (
            relative_to_media(media_dir, result.thumbnail_path) if result.thumbnail_path else None
        )
        video.filesize = result.file_path.stat().st_size
        video.width = result.width
        video.height = result.height
        video.vcodec = result.vcodec
        video.acodec = result.acodec
        video.subtitles.clear()
        db.flush()
        for sub in result.subtitles:
            video.subtitles.append(
                Subtitle(
                    lang=sub.lang,
                    label=subtitle_label(sub.lang, sub.is_auto),
                    is_auto=sub.is_auto,
                    file_path=relative_to_media(media_dir, sub.path),
                )
            )
        if result.sponsorblock_cut:
            video.sponsorblock_cut = True
            video.sponsor_segments.clear()
            if result.chapters is not None:
                video.chapters = result.chapters
            if result.duration_s:
                video.duration_s = result.duration_s
        video.status = VideoStatus.READY
        video.downloaded_at = utcnow()

    def _finish(self, db: Session, job: DownloadJob, video: Video, note: str | None = None) -> None:
        job.status = JobStatus.COMPLETED
        job.stage = None
        job.progress = 1.0
        job.speed = None
        job.eta = None
        job.error_kind = None
        job.error_message = note
        job.finished_at = utcnow()
        update_items_for_job(db, job.id, ItemState.DOWNLOADED, video_id=video.id)
        db.commit()
        log.info("Download fertig: %s (%s)", video.title, video.youtube_id)
        if self._connectivity:
            self._connectivity.report_success()
        if self.on_download_finished:
            self.on_download_finished()
        self._publish_job(db, job.id)
        db.refresh(video)
        self._events.publish("video.updated", video=video_payload(video))

    def _skip(self, job_id: int, youtube_id: str, reason: str) -> None:
        with self._session() as db:
            job = db.get(DownloadJob, job_id)
            if job is None:
                return
            job.status = JobStatus.SKIPPED
            job.youtube_id = youtube_id
            job.stage = None
            job.error_kind = None
            job.error_message = reason
            job.finished_at = utcnow()
            update_items_for_job(db, job_id, ItemState.FILTERED, reason=reason)
            db.commit()
            log.info("Download %s übersprungen: %s", job_id, reason)
            self._publish_job(db, job_id)

    def _handle_cancel(self, job_id: int, temp_dir: Any) -> None:
        with self._lock:
            reason = self._stop_reasons.pop(job_id, None)
        if self._stop.is_set():
            reason = "requeue"  # shutting down: resume after the restart
        reason = reason or "cancel"
        with self._session() as db:
            job = db.get(DownloadJob, job_id)
            if job is None:
                return
            if reason == "cancel":
                job.status = JobStatus.CANCELLED
                job.finished_at = utcnow()
                update_items_for_job(db, job_id, ItemState.REMOVED, reason="Abgebrochen")
            else:
                # Paused or re-queued: keep the partial files and don't count the attempt.
                job.status = JobStatus.PAUSED if reason == "pause" else JobStatus.QUEUED
                job.attempts = max(job.attempts - 1, 0)
            job.stage = None
            job.speed = None
            job.eta = None
            self._reset_video(
                db, job, VideoStatus.FAILED if reason == "cancel" else VideoStatus.PENDING
            )
            db.commit()
            self._publish_job(db, job_id)
        if reason == "cancel":
            cleanup_temp(temp_dir)
            log.info("Download %s abgebrochen", job_id)
        else:
            log.info("Download %s %s", job_id, "pausiert" if reason == "pause" else "eingereiht")

    def _handle_error(self, job_id: int, exc: Exception, temp_dir: Any) -> None:
        kind = classify_error(exc)
        message = clean_message(exc)
        with self._session() as db:
            job = db.get(DownloadJob, job_id)
            if job is None:
                return
            job.error_kind = kind
            job.error_message = message
            job.stage = None
            job.speed = None
            job.eta = None
            offline = (
                kind is ErrorKind.NETWORK
                and self._connectivity is not None
                and self._connectivity.confirm_offline()
            )
            if offline:
                # Not the video's fault: wait for the connection without using up attempts.
                job.attempts = max(job.attempts - 1, 0)
                job.status = JobStatus.QUEUED
                job.next_attempt_at = utcnow() + OFFLINE_RETRY
                job.error_message = OFFLINE_MESSAGE
                self._reset_video(db, job, VideoStatus.PENDING)
                log.info("Download %s wartet auf die Internetverbindung", job_id)
            elif is_retryable(kind) and job.attempts < job.max_attempts:
                delay = retry_delay(kind, job.attempts)
                job.status = JobStatus.QUEUED
                job.next_attempt_at = utcnow() + delay
                self._reset_video(db, job, VideoStatus.PENDING)
                log.warning(
                    "Download %s fehlgeschlagen (%s, Versuch %d/%d), neuer Versuch in %ds: %s",
                    job_id,
                    kind,
                    job.attempts,
                    job.max_attempts,
                    delay.total_seconds(),
                    message,
                )
            else:
                job.status = JobStatus.FAILED
                job.finished_at = utcnow()
                self._reset_video(db, job, VideoStatus.FAILED)
                update_items_for_job(db, job_id, ItemState.FAILED, reason=message[:255])
                log.error("Download %s endgültig fehlgeschlagen (%s): %s", job_id, kind, message)
                cleanup_temp(temp_dir)
            db.commit()
            self._publish_job(db, job_id)

    @staticmethod
    def _reset_video(db: Session, job: DownloadJob, status: VideoStatus) -> None:
        if job.video_id is None:
            return
        video = db.get(Video, job.video_id)
        if video is not None and video.status is not VideoStatus.READY:
            video.status = status

    def _publish_job(self, db: Session, job_id: int) -> None:
        job = load_job(db, job_id)
        if job is not None:
            self._events.publish("job.updated", job=job_payload(job))

    def _progress_reporter(self, job_id: int) -> Any:
        state = {"event": 0.0, "db": time.monotonic()}

        def report(progress: DownloadProgress) -> None:
            now = time.monotonic()
            stage_change = progress.stage == "postprocessing"
            if not stage_change and now - state["event"] < EVENT_INTERVAL:
                return
            state["event"] = now
            self._events.publish(
                "job.progress",
                job_id=job_id,
                stage=progress.stage,
                progress=round(progress.progress, 4),
                downloaded_bytes=progress.downloaded_bytes,
                total_bytes=progress.total_bytes,
                speed=progress.speed,
                eta=progress.eta,
            )
            if stage_change or now - state["db"] >= DB_PROGRESS_INTERVAL:
                state["db"] = now
                with self._session() as db:
                    job = db.get(DownloadJob, job_id)
                    if job is not None and job.status is JobStatus.RUNNING:
                        job.stage = JobStage(progress.stage)
                        job.progress = progress.progress
                        job.downloaded_bytes = progress.downloaded_bytes
                        job.total_bytes = progress.total_bytes
                        job.speed = progress.speed
                        job.eta = progress.eta
                        db.commit()

        return report
