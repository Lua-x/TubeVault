"""Works through the library in the background: seek previews and loudness per video.

One video at a time, newest first, with ffmpeg at the lowest CPU priority – playback
and downloads always come first. Each part is tried once per file; a new file (better
quality, re-download) is analysed again.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Video, VideoStatus
from app.services import analysis
from app.services.app_settings import AnalysisOptions
from app.services.library import UnsafePathError, resolve_media_path
from app.services.transcode import ProbeError, ffmpeg_binary, probe

log = logging.getLogger(__name__)

IDLE_WAIT_S = 120.0
TIMEOUT_S = 3600


@dataclass(frozen=True)
class AnalysisStatus:
    total: int
    trickplay_done: int
    loudness_done: int
    current: str | None


def _nice() -> list[str]:
    nice = shutil.which("nice")
    return [nice, "-n", "19"] if nice else []


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 – fixed binary, paths we chose
        [*_nice(), ffmpeg_binary(), *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )


class MediaAnalyzer:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        options: Callable[[], AnalysisOptions],
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._options = options
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: str | None = None

    # --- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="analyzer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def wake(self) -> None:
        self._wake.set()

    # --- files ---------------------------------------------------------------------------

    def directory(self, video_id: int) -> Path:
        return self._settings.trickplay_dir / str(video_id)

    def forget(self, video_id: int) -> None:
        """The file changed (or is gone): drop the results, analyse again."""
        shutil.rmtree(self.directory(video_id), ignore_errors=True)
        with self._sessions() as db:
            db.execute(
                update(Video)
                .where(Video.id == video_id)
                .values(trickplay=None, trickplay_at=None, loudness_lufs=None, loudness_at=None)
            )
            db.commit()
        self.wake()

    def remove(self, video_id: int) -> None:
        shutil.rmtree(self.directory(video_id), ignore_errors=True)

    # --- work ----------------------------------------------------------------------------

    def status(self) -> AnalysisStatus:
        with self._sessions() as db:
            ready = (Video.status == VideoStatus.READY, Video.file_path.is_not(None))
            total, trickplay, loudness = db.execute(
                select(
                    func.count(Video.id),
                    func.count(Video.trickplay_at),
                    func.count(Video.loudness_at),
                ).where(*ready)
            ).one()
        return AnalysisStatus(total, trickplay, loudness, self._current)

    def _next(self, options: AnalysisOptions) -> int | None:
        missing = []
        if options.trickplay:
            missing.append(Video.trickplay_at.is_(None))
        if options.loudness:
            missing.append(Video.loudness_at.is_(None))
        if not missing:
            return None
        with self._sessions() as db:
            return db.scalar(
                select(Video.id)
                .where(
                    Video.status == VideoStatus.READY, Video.file_path.is_not(None), or_(*missing)
                )
                .order_by(Video.added_at.desc(), Video.id.desc())
                .limit(1)
            )

    def run_once(self) -> bool:
        """Analyses the next video; False when there is nothing left to do."""
        options = self._options()
        video_id = self._next(options)
        if video_id is None:
            return False
        self.analyse(video_id, options)
        return True

    def analyse(self, video_id: int, options: AnalysisOptions) -> None:
        with self._sessions() as db:
            video = db.get(Video, video_id)
            if video is None or not video.file_path:
                return
            title, relative = video.title, video.file_path
            need_trickplay = options.trickplay and video.trickplay_at is None
            need_loudness = options.loudness and video.loudness_at is None
        self._current = title
        try:
            source = resolve_media_path(self._settings.media_dir, relative)
            info = probe(source) if source.is_file() else None
        except (UnsafePathError, ProbeError, OSError) as exc:
            log.info("Analyse von %s übersprungen: %s", title, exc)
            info = None
        values: dict[str, object] = {}
        now = datetime.now(UTC)
        if need_loudness:
            values["loudness_lufs"] = self._loudness(source) if info and info.audio_codec else None
            values["loudness_at"] = now
        if need_trickplay:
            trickplay = None
            if info and info.video_codec:
                trickplay = self._trickplay(
                    video_id, source, info.duration, info.width, info.height
                )
            values["trickplay"] = trickplay.as_json() if trickplay else None
            values["trickplay_at"] = now
        self._current = None
        if values:
            with self._sessions() as db:
                db.execute(update(Video).where(Video.id == video_id).values(**values))
                db.commit()

    def _loudness(self, source: Path) -> float | None:
        try:
            result = _run(analysis.loudness_args(source))
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("Lautheit von %s nicht messbar: %s", source.name, exc)
            return None
        return analysis.parse_loudness(result.stderr) if result.returncode == 0 else None

    def _trickplay(
        self,
        video_id: int,
        source: Path,
        duration: float,
        width: int | None,
        height: int | None,
    ) -> analysis.Trickplay | None:
        plan = analysis.plan(duration, width, height)
        target = self.directory(video_id)
        partial = target.with_name(f"{video_id}.partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True, exist_ok=True)
        try:
            result = _run(analysis.trickplay_args(source, partial, plan))
            made = len(list(partial.glob("*.jpg")))
            if result.returncode != 0 or made == 0:
                log.info(
                    "Vorschaubilder für %s fehlgeschlagen: %s", source.name, result.stderr[-300:]
                )
                return None
            shutil.rmtree(target, ignore_errors=True)
            partial.rename(target)
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("Vorschaubilder für %s fehlgeschlagen: %s", source.name, exc)
            return None
        finally:
            shutil.rmtree(partial, ignore_errors=True)
        # Fewer sheets than planned (keyframes far apart at the end): count what exists.
        count = min(plan.count, made * plan.columns * plan.rows)
        return analysis.Trickplay(**{**plan.as_json(), "count": count})

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                busy = self.run_once()
            except Exception:
                log.exception("Fehler in der Medienanalyse")
                busy = False
            if not busy:
                self._wake.wait(IDLE_WAIT_S)
                self._wake.clear()
