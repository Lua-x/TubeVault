"""Long-running library jobs (moving files, writing NFOs, imports, maintenance).

Only one runs at a time. Progress goes out as `library.task` events, so the settings page
and the admin dashboard can show it live.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.models import Channel, Setting, Video, VideoStatus
from app.services import nfo
from app.services.app_settings import LibraryOptions, load_app_settings
from app.services.relayout import move_video, prune_empty_dirs

log = logging.getLogger(__name__)

NFO_STATE_KEY = "nfo_layout"
PUBLISH_INTERVAL_S = 0.5


class TaskBusyError(RuntimeError):
    pass


@dataclass
class TaskState:
    kind: str
    label: str
    state: Literal["running", "done", "failed"] = "running"
    done: int = 0
    total: int = 0
    message: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Progress:
    """Handed to a task; counts steps and publishes at a sane rate."""

    def __init__(self, state: TaskState, publish: Callable[[], None]) -> None:
        self._state = state
        self._publish = publish
        self._last = 0.0

    def total(self, value: int) -> None:
        self._state.total = value
        self._publish()

    def phase(self, total: int) -> None:
        """Starts counting again, e.g. for the second pass or the NFO step."""
        self._state.done = 0
        self.total(total)

    def step(self, message: str | None = None) -> None:
        self._state.done += 1
        if message:
            self._state.message = message
        now = time.monotonic()
        if now - self._last >= PUBLISH_INTERVAL_S:
            self._last = now
            self._publish()


Work = Callable[[Progress], str | None]


class LibraryTasks:
    def __init__(
        self, settings: Settings, sessions: sessionmaker[Session], events: EventBus
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._events = events
        self._lock = threading.Lock()
        self._state: TaskState | None = None
        self._thread: threading.Thread | None = None

    @property
    def current(self) -> TaskState | None:
        return self._state

    def busy(self) -> bool:
        return self._state is not None and self._state.state == "running"

    def run(self, kind: str, label: str, work: Work) -> TaskState:
        with self._lock:
            if self.busy():
                assert self._state is not None
                raise TaskBusyError(f"Gerade läuft: {self._state.label}")
            state = TaskState(kind=kind, label=label)
            self._state = state
            self._thread = threading.Thread(
                target=self._execute, args=(state, work), name=f"task-{kind}", daemon=True
            )
            self._thread.start()
        self._publish()
        return state

    def wait(self, timeout: float = 30.0) -> None:
        """For tests and shutdown."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _execute(self, state: TaskState, work: Work) -> None:
        log.info("Aufgabe gestartet: %s", state.label)
        try:
            state.message = work(Progress(state, self._publish))
            state.state = "done"
            log.info("Aufgabe fertig: %s (%s)", state.label, state.message or "ok")
        except Exception as exc:
            log.exception("Aufgabe fehlgeschlagen: %s", state.label)
            state.state = "failed"
            state.message = str(exc) or exc.__class__.__name__
        state.finished_at = datetime.now(UTC).isoformat()
        self._publish()

    def _publish(self) -> None:
        if self._state is not None:
            self._events.publish("library.task", task=self._state.as_dict())

    # --- concrete tasks ------------------------------------------------------------------

    def _ready_videos(self, db: Session) -> list[Video]:
        return list(
            db.scalars(
                select(Video)
                .where(Video.status == VideoStatus.READY, Video.file_path.is_not(None))
                .options(selectinload(Video.subtitles), selectinload(Video.channel))
                .order_by(Video.id)
            )
        )

    def relayout(self, options: LibraryOptions) -> TaskState:
        """Moves every video into the chosen layout and refreshes NFOs on the way."""
        media_dir = self._settings.media_dir

        def work(progress: Progress) -> str:
            moved = 0
            with self._sessions() as db:
                # Two passes: downloads that started before the switch land in the old layout.
                for _ in range(2):
                    videos = self._ready_videos(db)
                    progress.phase(len(videos))
                    folders = set()
                    for video in videos:
                        old_folder = move_video(media_dir, video, options.layout)
                        if old_folder is not None:
                            folders.add(old_folder)
                            moved += 1
                            db.commit()
                        progress.step(video.title)
                    prune_empty_dirs(media_dir, folders)
                    if not folders:
                        break
                self._sync_nfo(db, options, progress)
            return f"{moved} Videos verschoben"

        label = "Bibliothek ins Serien-Schema umziehen"
        if options.layout == "tubevault":
            label = "Bibliothek ins TubeVault-Schema umziehen"
        return self.run("relayout", label, work)

    def sync_nfo(self, options: LibraryOptions) -> TaskState:
        """Writes (or removes) NFO files for the whole library."""

        def work(progress: Progress) -> str:
            with self._sessions() as db:
                return self._sync_nfo(db, options, progress)

        label = "NFO-Dateien schreiben" if options.write_nfo else "NFO-Dateien entfernen"
        return self.run("nfo", label, work)

    def _sync_nfo(self, db: Session, options: LibraryOptions, progress: Progress) -> str:
        media_dir = self._settings.media_dir
        videos = self._ready_videos(db)
        progress.phase(len(videos))
        for video in videos:
            if options.write_nfo:
                nfo.write_video_nfo(db, media_dir, video, options.layout)
            else:
                nfo.remove_video_nfo(media_dir, video)
            progress.step(video.title)
        for channel in db.scalars(select(Channel)):
            if options.write_nfo and options.layout == "series":
                nfo.write_channel_files(media_dir, channel)
            else:
                nfo.remove_channel_files(media_dir, channel)
        _set(db, NFO_STATE_KEY, options.layout if options.write_nfo else None)
        return f"{len(videos)} Videos"

    def backfill_nfo_if_needed(self) -> None:
        """After an update or a crash: make sure the NFOs match the settings."""
        with self._sessions() as db:
            options = load_app_settings(db).library
            row = db.get(Setting, NFO_STATE_KEY)
            current = row.value if row else None
        wanted = options.layout if options.write_nfo else None
        if current != wanted and not self.busy():
            self.sync_nfo(options)


def _set(db: Session, key: str, value: object) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()
