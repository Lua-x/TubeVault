"""Turns speech into subtitles, one video at a time, in the background.

Videos are queued by an admin (per video, or all own videos without subtitles) or, if
wanted, right after an import. The queue lives in memory: after a restart the button
"Eigene Videos ohne Untertitel" queues what is still missing.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.models import Subtitle, Video, VideoStatus
from app.models.video import LOCAL_PREFIX
from app.services.app_settings import SpeechOptions
from app.services.languages import subtitle_label
from app.services.library import UnsafePathError, relative_to_media, resolve_media_path
from app.services.speech import (
    Speech,
    SpeechError,
    is_speech,
    speech_file,
    speech_lang,
)

log = logging.getLogger(__name__)

MAX_QUEUE = 5000


@dataclass(frozen=True)
class SpeechStatus:
    current: str | None
    queued: int
    last_error: str | None


def speech_label(language: str) -> str:
    return f"{subtitle_label(language, False)} (Spracherkennung)"


def remove_speech_subtitles(media_dir: Path, video: Video) -> None:
    """Drops earlier speech subtitles of a video, file and row."""
    for sub in [s for s in video.subtitles if is_speech(s.lang)]:
        try:
            resolve_media_path(media_dir, sub.file_path).unlink(missing_ok=True)
        except (UnsafePathError, OSError) as exc:
            log.info("Alte Spracherkennung nicht gelöscht: %s", exc)
        video.subtitles.remove(sub)


class SpeechWorker:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        events: EventBus,
        speech: Speech,
        options: Callable[[], SpeechOptions],
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._events = events
        self.speech = speech
        self._options = options
        self._lock = threading.Lock()
        self._queue: deque[int] = deque()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: str | None = None
        self._last_error: str | None = None

    # --- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="speech", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.speech.cancel()
        if self._thread is not None:
            self._thread.join(5)

    # --- queue ---------------------------------------------------------------------------

    def ready(self) -> bool:
        return self.speech.ready(self._options().model)

    def enqueue(self, video_ids: Iterable[int]) -> int:
        """Queues videos (each once); returns how many were added."""
        added = 0
        with self._lock:
            for video_id in video_ids:
                if video_id not in self._queue and len(self._queue) < MAX_QUEUE:
                    self._queue.append(video_id)
                    added += 1
        if added:
            self._wake.set()
        return added

    def own_videos_without_subtitles(self) -> list[int]:
        with self._sessions() as db:
            return list(
                db.scalars(
                    select(Video.id)
                    .where(
                        Video.youtube_id.startswith(LOCAL_PREFIX),
                        Video.status == VideoStatus.READY,
                        Video.file_path.is_not(None),
                        ~exists().where(Subtitle.video_id == Video.id),
                    )
                    .order_by(Video.added_at.desc(), Video.id.desc())
                )
            )

    def status(self) -> SpeechStatus:
        with self._lock:
            queued = len(self._queue)
        return SpeechStatus(self._current, queued, self._last_error)

    # --- work ----------------------------------------------------------------------------

    def run_once(self) -> bool:
        """Works on the next queued video; False when the queue is empty."""
        with self._lock:
            if not self._queue:
                return False
            video_id = self._queue.popleft()
        try:
            self.transcribe(video_id)
        except SpeechError as exc:
            self._last_error = str(exc)
        return True

    def transcribe(self, video_id: int) -> None:
        options = self._options()
        media_dir = self._settings.media_dir
        with self._sessions() as db:
            video = db.get(Video, video_id)
            if video is None or video.status != VideoStatus.READY or not video.file_path:
                return
            title, relative = video.title, video.file_path
        self._current = title
        partial = self._settings.temp_dir / f"speech-{video_id}.vtt"
        try:
            try:
                source = resolve_media_path(media_dir, relative)
            except UnsafePathError as exc:
                raise SpeechError(f"„{title}“: Datei liegt nicht unter /media") from exc
            if not source.is_file():
                raise SpeechError(f"„{title}“: Datei fehlt")
            partial.parent.mkdir(parents=True, exist_ok=True)
            language = None if options.language == "auto" else options.language
            try:
                result = self.speech.transcribe(options.model, source, partial, language)
            except SpeechError as exc:
                raise SpeechError(f"„{title}“: {exc}") from exc
            if "-->" not in partial.read_text(encoding="utf-8"):
                raise SpeechError(f"„{title}“: Keine Sprache erkannt")
            self._store(video_id, partial, result.language)
            self._last_error = None
            log.info("Untertitel per Spracherkennung für %s (%s)", title, result.language)
        finally:
            partial.unlink(missing_ok=True)
            self._current = None

    def _store(self, video_id: int, partial: Path, language: str) -> None:
        media_dir = self._settings.media_dir
        with self._sessions() as db:
            video = db.scalar(
                select(Video).where(Video.id == video_id).options(selectinload(Video.subtitles))
            )
            # Deleted or replaced while we listened: nothing to attach to.
            if video is None or not video.file_path:
                return
            target = speech_file(resolve_media_path(media_dir, video.file_path), language)
            remove_speech_subtitles(media_dir, video)
            db.flush()
            os.replace(partial, target)
            video.subtitles.append(
                Subtitle(
                    lang=speech_lang(language),
                    label=speech_label(language),
                    is_auto=True,
                    file_path=relative_to_media(media_dir, target),
                )
            )
            db.commit()
        self._events.publish("video.updated", video={"id": video_id})

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                busy = self.run_once()
            except Exception:
                log.exception("Fehler in der Spracherkennung")
                busy = True
            if not busy:
                self._wake.wait()
                self._wake.clear()
