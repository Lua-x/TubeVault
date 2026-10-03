"""Comments are optional: saved after a download when wanted, or later on request.

They come from a separate request to YouTube, so a failure never costs the video.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import classify_error
from app.core.events import EventBus
from app.db import utcnow
from app.models import Comment, ErrorKind, Video
from app.services.connectivity import Connectivity
from app.services.downloader import CommentsResult, Downloader
from app.services.upgrades import watch_url

log = logging.getLogger(__name__)

OFFLINE_MESSAGE = "Keine Internetverbindung – Kommentare lassen sich gerade nicht laden."


def store_comments(db: Session, video: Video, result: CommentsResult) -> int:
    """Replaces the saved comments of a video; returns how many were kept."""
    db.execute(delete(Comment).where(Comment.video_id == video.id))
    seen: set[str] = set()
    for position, item in enumerate(result.comments):
        if item.youtube_id in seen:
            continue
        seen.add(item.youtube_id)
        db.add(
            Comment(
                video_id=video.id,
                youtube_id=item.youtube_id[:128],
                parent_id=item.parent_id[:128] if item.parent_id else None,
                position=position,
                author=item.author[:255],
                author_is_uploader=item.author_is_uploader,
                author_is_verified=item.author_is_verified,
                text=item.text,
                like_count=item.like_count,
                published_at=item.published_at,
                is_pinned=item.is_pinned,
                is_favorited=item.is_favorited,
            )
        )
    video.comments_fetched_at = utcnow()
    video.comment_count = result.total if result.total is not None else len(seen)
    db.commit()
    return len(seen)


def _message(exc: BaseException) -> str:
    kind = classify_error(exc)
    if kind is ErrorKind.NETWORK:
        return OFFLINE_MESSAGE
    if kind is ErrorKind.RATE_LIMITED:
        return "YouTube bremst gerade – später noch einmal versuchen."
    text = str(exc).removeprefix("ERROR: ").strip()
    return f"Kommentare konnten nicht geladen werden: {text[:300]}"


class CommentFetcher:
    """Fetches comments one video at a time in the background."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        downloader: Downloader,
        events: EventBus,
        connectivity: Connectivity | None = None,
    ) -> None:
        self._sessions = sessions
        self._downloader = downloader
        self._events = events
        self._connectivity = connectivity
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comments")
        self._lock = threading.Lock()
        self._pending: set[int] = set()
        self._errors: dict[int, str] = {}

    def request(self, video_id: int, limit: int) -> bool:
        """Queues a fetch; False when one is already waiting or running for this video."""
        with self._lock:
            if video_id in self._pending:
                return False
            self._pending.add(video_id)
            self._errors.pop(video_id, None)
        self._executor.submit(self._run, video_id, limit)
        return True

    def state(self, video_id: int) -> tuple[bool, str | None]:
        """(fetching, last error) for a video."""
        with self._lock:
            return video_id in self._pending, self._errors.get(video_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, video_id: int, limit: int) -> None:
        try:
            self._fetch(video_id, limit)
        except Exception as exc:  # never let the worker die
            log.exception("Kommentare für Video %s fehlgeschlagen", video_id)
            with self._lock:
                self._errors[video_id] = _message(exc)
        finally:
            with self._lock:
                self._pending.discard(video_id)
            self._events.publish("video.comments", video_id=video_id)

    def _fetch(self, video_id: int, limit: int) -> None:
        if self._connectivity is not None and self._connectivity.should_wait():
            with self._lock:
                self._errors[video_id] = OFFLINE_MESSAGE
            return
        with self._sessions() as db:
            video = db.get(Video, video_id)
            if video is None:
                return
            url = watch_url(video)
        try:
            result = self._downloader.fetch_comments(url, limit)
        except Exception as exc:
            log.warning("Kommentare für %s konnten nicht geladen werden: %s", url, exc)
            if (
                classify_error(exc) is ErrorKind.NETWORK
                and self._connectivity is not None
                and not self._connectivity.confirm_offline()
            ):
                message = "Die Verbindung zu YouTube ist abgebrochen – bitte noch einmal versuchen."
            else:
                message = _message(exc)
            with self._lock:
                self._errors[video_id] = message
            return
        if self._connectivity is not None:
            self._connectivity.report_success()
        with self._sessions() as db:
            video = db.get(Video, video_id)
            if video is not None:
                count = store_comments(db, video, result)
                log.info("%s Kommentare gespeichert: %s", count, video.title)
