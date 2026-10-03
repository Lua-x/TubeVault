"""Runs ffmpeg for HLS sessions and remuxes, and keeps the cache within its limit.

A *session* belongs to one video in one quality. Its segments live in a cache folder and are
reused by later viewers. ffmpeg runs only while someone watches: it is paused when it gets too
far ahead, restarted at another segment when the viewer seeks, and stopped when nobody asks
for segments anymore.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import Settings
from app.services.app_settings import TranscodeOptions
from app.services.transcode import (
    FALLBACKS,
    HlsJob,
    MediaInfo,
    Mode,
    audio_command,
    can_copy_into_mp4,
    device_command,
    ffmpeg_binary,
    hls_command,
    hwaccel_test_command,
    remux_command,
    segment_count,
    segment_name,
    target_height,
)

log = logging.getLogger(__name__)

# A request at most this far beyond the newest segment waits for the running ffmpeg.
LOOKAHEAD = 3
# Pause ffmpeg when it is this many segments ahead of the viewer, resume below RESUME_AHEAD.
PAUSE_AHEAD = 20
RESUME_AHEAD = 10
IDLE_STOP_S = 90.0
FORGET_S = 3600.0
SEGMENT_TIMEOUT_S = 60.0
EVICT_IDLE_S = 20.0
CLEANUP_INTERVAL_S = 600.0
MAX_CACHE_AGE_S = 30 * 86400.0
# Repacking, compact copies and sound extraction running at the same time; more wait.
FILE_JOBS = 2
# What a cached file holds: the original repacked (None), a compact copy of that height,
# or only the sound.
Variant = int | Literal["audio"] | None


class TranscodeError(RuntimeError):
    pass


class TooManySessionsError(TranscodeError):
    pass


def file_signature(path: Path) -> str:
    """Changes when the file is replaced, so stale cache entries are never served."""
    stat = path.stat()
    raw = f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()[:10]


def file_key(video_id: int, path: Path, variant: Variant) -> str:
    key = f"{video_id}-{file_signature(path)}"
    if variant is None:
        return key
    return f"{key}-audio" if variant == "audio" else f"{key}-h{variant}"


def _touch(path: Path) -> None:
    with contextlib.suppress(OSError):
        os.utime(path)


def _tail(path: Path | None, lines: int = 6) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        text = path.read_text(errors="replace").strip().splitlines()
    except OSError:
        return ""
    return "\n".join(text[-lines:])


@dataclass(frozen=True)
class Source:
    video_id: int
    path: Path
    info: MediaInfo


@dataclass
class HlsSession:
    key: str
    source: Source
    quality: str
    height: int
    directory: Path
    modes: tuple[Mode, ...]
    vaapi_device: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    process: subprocess.Popen[bytes] | None = None
    start_segment: int = 0
    mode_index: int = 0
    last_request: float = field(default_factory=time.monotonic)
    last_index: int = 0
    paused: bool = False
    evicted: bool = False
    _newest: int = -1

    @property
    def count(self) -> int:
        return segment_count(self.source.info.duration)

    @property
    def mode(self) -> Mode:
        return self.modes[self.mode_index]

    @property
    def log_path(self) -> Path:
        return self.directory / "ffmpeg.log"

    def segment_path(self, index: int) -> Path:
        return self.directory / segment_name(index)

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def newest(self) -> int:
        """Highest complete segment of the current run (start_segment - 1 if none yet)."""
        index = max(self._newest, self.start_segment - 1)
        while index + 1 < self.count and self.segment_path(index + 1).exists():
            index += 1
        self._newest = index
        return index


@dataclass
class RemuxJob:
    key: str
    target: Path
    duration: float
    state: Literal["running", "ready", "failed"] = "running"
    progress: float = 0.0
    error: str | None = None
    process: subprocess.Popen[str] | None = None


@dataclass(frozen=True)
class SessionInfo:
    video_id: int
    quality: str
    height: int
    mode: Mode
    position_s: float
    paused: bool
    idle_s: float


class Transcoder:
    def __init__(self, settings: Settings, options: Callable[[], TranscodeOptions]) -> None:
        self._settings = settings
        self._options = options
        self._sessions: dict[str, HlsSession] = {}
        self._remuxes: dict[str, RemuxJob] = {}
        self._file_slots = threading.BoundedSemaphore(FILE_JOBS)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cleanup = 0.0

    @property
    def hls_dir(self) -> Path:
        return self._settings.cache_dir / "hls"

    @property
    def remux_dir(self) -> Path:
        return self._settings.cache_dir / "remux"

    # --- lifecycle --------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="transcoder", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        with self._lock:
            sessions = list(self._sessions.values())
            remuxes = list(self._remuxes.values())
        for session in sessions:
            with session.lock:
                self._kill(session)
        for job in remuxes:
            if job.process and job.process.poll() is None:
                job.process.kill()

    def _loop(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self._reap()
                if time.monotonic() - self._last_cleanup > CLEANUP_INTERVAL_S:
                    self.cleanup_cache()
            except Exception:
                log.exception("Fehler in der Umwandlungs-Verwaltung")

    # --- HLS ---------------------------------------------------------------------------

    def session(self, source: Source, quality: str) -> HlsSession:
        options = self._options()
        height = target_height(quality, source.info.height, options.max_height)
        signature = file_signature(source.path)
        key = f"{source.video_id}-{quality}-{height}-{signature}-{options.hwaccel}"
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                directory = self.hls_dir / key
                directory.mkdir(parents=True, exist_ok=True)
                for leftover in directory.glob("*.tmp"):
                    leftover.unlink(missing_ok=True)
                session = HlsSession(
                    key=key,
                    source=source,
                    quality=quality,
                    height=height,
                    directory=directory,
                    modes=FALLBACKS[options.hwaccel],
                    vaapi_device=options.vaapi_device,
                )
                self._sessions[key] = session
        _touch(session.directory)
        return session

    def segment(self, source: Source, quality: str, index: int) -> Path:
        """Path of a finished segment; starts or moves ffmpeg and waits when needed."""
        session = self.session(source, quality)
        if not 0 <= index < session.count:
            raise IndexError(index)
        path = session.segment_path(index)
        with session.lock:
            session.last_request = time.monotonic()
            session.last_index = index
            session.evicted = False
            if not path.exists() and (
                not session.running()
                or index < session.start_segment
                or index > session.newest() + LOOKAHEAD
            ):
                self._launch(session, index)
            self._resume_if_close(session)
        return path if path.exists() else self._wait(session, index)

    def _wait(self, session: HlsSession, index: int) -> Path:
        path = session.segment_path(index)
        deadline = time.monotonic() + SEGMENT_TIMEOUT_S
        while not path.exists():
            with session.lock:
                if path.exists():
                    break
                if session.evicted:
                    raise TooManySessionsError("Umwandlung zugunsten eines anderen Videos beendet")
                if index < session.start_segment and session.running():
                    # Another viewer moved this session elsewhere; take it back.
                    self._launch(session, index)
                elif not session.running():
                    self._after_exit(session, index)
            if time.monotonic() > deadline:
                raise TranscodeError("Zeitüberschreitung bei der Umwandlung")
            time.sleep(0.1)
        return path

    def _after_exit(self, session: HlsSession, index: int) -> None:
        """ffmpeg ended without writing the segment: fall back to a slower mode or give up."""
        code = session.process.returncode if session.process else None
        produced = session.newest() >= session.start_segment
        if code not in (0, None) and not produced and session.mode_index + 1 < len(session.modes):
            log.warning(
                "Umwandlung mit %s fehlgeschlagen, versuche %s: %s",
                session.mode,
                session.modes[session.mode_index + 1],
                _tail(session.log_path, 2),
            )
            session.mode_index += 1
            self._launch(session, index)
        elif code in (0, None) and index >= session.start_segment and produced:
            # Finished (or was stopped) before reaching this segment: continue from there.
            self._launch(session, index)
        else:
            detail = _tail(session.log_path) or f"ffmpeg beendet mit Code {code}"
            raise TranscodeError(f"Umwandlung fehlgeschlagen: {detail}")

    def _launch(self, session: HlsSession, index: int) -> None:
        self._kill(session)
        self._ensure_capacity(session)
        job = HlsJob(
            source=session.source.path,
            directory=session.directory,
            start_segment=index,
            height=session.height,
            source_height=session.source.info.height,
            mode=session.mode,
            vaapi_device=session.vaapi_device,
        )
        with session.log_path.open("wb") as log_file:
            session.process = subprocess.Popen(  # noqa: S603 – arguments built from validated input
                hls_command(job),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log_file,
                start_new_session=True,
            )
        session.start_segment = index
        session._newest = index - 1
        session.paused = False
        log.info(
            "Umwandlung: Video %s, %sp ab %s s (%s)",
            session.source.video_id,
            session.height,
            index * 6,
            session.mode,
        )

    def _kill(self, session: HlsSession) -> None:
        process = session.process
        if process is not None and process.poll() is None:
            # SIGKILL on purpose: on SIGTERM ffmpeg would finish the segment it is writing and
            # publish a truncated file. Killed, the half-written .tmp is simply dropped.
            process.kill()
            process.wait()
        session.process = None
        session.paused = False
        for leftover in session.directory.glob("*.tmp"):
            leftover.unlink(missing_ok=True)

    def _ensure_capacity(self, session: HlsSession) -> None:
        limit = self._options().max_sessions
        with self._lock:
            others = [s for s in self._sessions.values() if s is not session and s.running()]
        if len(others) < limit:
            return
        now = time.monotonic()
        oldest = min(others, key=lambda s: s.last_request)
        if now - oldest.last_request < EVICT_IDLE_S:
            raise TooManySessionsError(
                f"Es laufen schon {len(others)} Umwandlungen. Versuch es gleich noch einmal."
            )
        oldest.evicted = True
        process = oldest.process
        if process is not None and process.poll() is None:
            process.kill()

    def _resume_if_close(self, session: HlsSession) -> None:
        if (
            session.paused
            and session.process is not None
            and session.newest() - session.last_index < RESUME_AHEAD
        ):
            session.process.send_signal(signal.SIGCONT)
            session.paused = False

    def _reap(self) -> None:
        now = time.monotonic()
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            if not session.lock.acquire(timeout=0.5):
                continue
            try:
                if session.running():
                    assert session.process is not None
                    ahead = session.newest() - session.last_index
                    if now - session.last_request > IDLE_STOP_S:
                        log.info("Umwandlung von Video %s beendet", session.source.video_id)
                        self._kill(session)
                    elif not session.paused and ahead > PAUSE_AHEAD:
                        session.process.send_signal(signal.SIGSTOP)
                        session.paused = True
                    else:
                        self._resume_if_close(session)
                elif now - session.last_request > FORGET_S:
                    with self._lock:
                        self._sessions.pop(session.key, None)
            finally:
                session.lock.release()

    def sessions(self) -> list[SessionInfo]:
        now = time.monotonic()
        with self._lock:
            sessions = [s for s in self._sessions.values() if s.running()]
        return [
            SessionInfo(
                video_id=s.source.video_id,
                quality=s.quality,
                height=s.height,
                mode=s.mode,
                position_s=s.last_index * 6.0,
                paused=s.paused,
                idle_s=now - s.last_request,
            )
            for s in sessions
        ]

    # --- remux ---------------------------------------------------------------------------

    @staticmethod
    def _file_key(source: Source, variant: Variant) -> str:
        return file_key(source.video_id, source.path, variant)

    def _target(self, key: str, variant: Variant) -> Path:
        return self.remux_dir / f"{key}{'.m4a' if variant == 'audio' else '.mp4'}"

    def remux(self, source: Source) -> RemuxJob:
        """Starts (or reports) copying the streams into an MP4 in the cache."""
        return self._file_job(source, None)

    def device(self, source: Source, height: int) -> RemuxJob:
        """Starts (or reports) a compact H.264 MP4 for saving onto a device."""
        return self._file_job(source, height)

    def audio(self, source: Source) -> RemuxJob:
        """Starts (or reports) the sound alone as M4A – for listening and podcasts."""
        return self._file_job(source, "audio")

    def _file_job(self, source: Source, variant: Variant) -> RemuxJob:
        key = self._file_key(source, variant)
        target = self._target(key, variant)
        with self._lock:
            job = self._remuxes.get(key)
            if target.is_file():
                _touch(target)
                if job is None or job.state != "ready":
                    job = RemuxJob(key=key, target=target, duration=source.info.duration)
                    job.state, job.progress = "ready", 1.0
                    self._remuxes[key] = job
                return job
            if job is not None and job.state == "running":
                return job
            if variant is None and not can_copy_into_mp4(source.info):
                raise TranscodeError("Diese Codecs lassen sich nicht in MP4 kopieren")
            if variant == "audio" and not source.info.audio_codec:
                raise TranscodeError("Dieses Video hat keine Tonspur")
            self.remux_dir.mkdir(parents=True, exist_ok=True)
            job = RemuxJob(key=key, target=target, duration=source.info.duration)
            self._remuxes[key] = job
        partial = target.with_name(f"{key}.partial{target.suffix}")
        if variant is None:
            command = remux_command(source.path, partial, source.info.video_codec)
            label = "Umverpacken"
        elif variant == "audio":
            command = audio_command(source.path, partial, source.info.audio_codec)
            label = "Tonspur"
        else:
            command = device_command(source.path, partial, variant, source.info.height)
            label = f"Gerätefassung {variant}p"
        threading.Thread(
            target=self._run_file_job,
            args=(job, command, partial, f"{label}: Video {source.video_id}"),
            name="remux",
            daemon=True,
        ).start()
        return job

    def _run_file_job(self, job: RemuxJob, command: list[str], partial: Path, label: str) -> None:
        """Runs when a slot is free: a podcast app fetching ten episodes at once must not
        start ten ffmpeg processes on a small server. Waiting jobs report progress 0."""
        with self._file_slots:
            if self._stop.is_set():
                job.state, job.error = "failed", "TubeVault wird beendet"
                return
            log.info(label)
            log_path = job.target.with_name(f"{job.key}.log")
            with log_path.open("wb") as log_file:
                job.process = subprocess.Popen(  # noqa: S603 – arguments built from validated input
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=log_file,
                    text=True,
                    start_new_session=True,
                )
            self._follow_remux(job, partial, log_path)

    def _follow_remux(self, job: RemuxJob, partial: Path, log_path: Path) -> None:
        process = job.process
        assert process is not None and process.stdout is not None
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit() and job.duration > 0:
                job.progress = min(0.99, int(value) / 1e6 / job.duration)
        code = process.wait()
        if code == 0 and partial.is_file():
            partial.replace(job.target)
            job.state, job.progress = "ready", 1.0
            log_path.unlink(missing_ok=True)
        else:
            job.state = "failed"
            job.error = _tail(log_path) or f"ffmpeg beendet mit Code {code}"
            partial.unlink(missing_ok=True)
            log.warning("Umverpacken fehlgeschlagen: %s", job.error)

    def remux_status(self, source: Source, variant: Variant = None) -> RemuxJob | None:
        key = self._file_key(source, variant)
        with self._lock:
            job = self._remuxes.get(key)
        if job is None and self._target(key, variant).is_file():
            return self._file_job(source, variant)
        return job

    def cached_audio(self, video_id: int, path: Path) -> Path | None:
        """The prepared sound of a file, if there is one – without probing the file."""
        target = self._target(file_key(video_id, path, "audio"), "audio")
        return target if target.is_file() else None

    def remux_file(self, source: Source, variant: Variant = None) -> Path | None:
        key = self._file_key(source, variant)
        target = self._target(key, variant)
        if not target.is_file():
            return None
        _touch(target)
        return target

    # --- cache ---------------------------------------------------------------------------

    def purge(self, video_id: int) -> None:
        """Drops everything cached for a video (e.g. after it was deleted)."""
        prefix = f"{video_id}-"
        with self._lock:
            doomed = [s for k, s in self._sessions.items() if k.startswith(prefix)]
            for session in doomed:
                self._sessions.pop(session.key, None)
        for session in doomed:
            with session.lock:
                self._kill(session)
        for directory in self.hls_dir.glob(f"{prefix}*"):
            shutil.rmtree(directory, ignore_errors=True)
        for file in self.remux_dir.glob(f"{prefix}*"):
            file.unlink(missing_ok=True)

    def cleanup_cache(self, limit: int | None = None) -> int:
        """Deletes least recently used entries above the size limit; returns bytes freed."""
        self._last_cleanup = time.monotonic()
        if limit is None:
            limit = self._options().cache_gb * 1024**3
        with self._lock:
            active = {s.directory for s in self._sessions.values() if s.running()}
            active |= {j.target for j in self._remuxes.values() if j.state == "running"}
        entries: list[tuple[float, int, Path]] = []
        if self.hls_dir.is_dir():
            for directory in self.hls_dir.iterdir():
                if directory.is_dir() and directory not in active:
                    size = sum(f.stat().st_size for f in directory.iterdir() if f.is_file())
                    entries.append((directory.stat().st_mtime, size, directory))
        if self.remux_dir.is_dir():
            for file in [*self.remux_dir.glob("*.mp4"), *self.remux_dir.glob("*.m4a")]:
                if file not in active and ".partial." not in file.name:
                    entries.append((file.stat().st_mtime, file.stat().st_size, file))
        total = sum(size for _, size, _ in entries)
        now = time.time()
        freed = 0
        for mtime, size, path in sorted(entries):
            if total <= limit and now - mtime < MAX_CACHE_AGE_S:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            total -= size
            freed += size
        if freed:
            log.info("Umwandlungs-Cache: %.1f MB freigegeben", freed / 1024**2)
        return freed

    def cache_size(self) -> int:
        root = self._settings.cache_dir
        if not root.is_dir():
            return 0
        return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())


# --- hardware ------------------------------------------------------------------------


@dataclass(frozen=True)
class HardwareInfo:
    render_devices: list[str]
    nvidia: bool
    encoders: dict[str, bool]


def detect_hardware() -> HardwareInfo:
    dri = Path("/dev/dri")
    devices = sorted(str(p) for p in dri.glob("renderD*")) if dri.is_dir() else []
    nvidia = Path("/dev/nvidiactl").exists() or any(Path("/dev").glob("nvidia[0-9]*"))
    wanted = ("libx264", "h264_vaapi", "h264_nvenc")
    found: set[str] = set()
    try:
        output = subprocess.run(  # noqa: S603 – fixed arguments
            [ffmpeg_binary(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        ).stdout
        found = {line.split()[1] for line in output.splitlines() if len(line.split()) > 1}
    except (OSError, subprocess.SubprocessError):
        pass
    return HardwareInfo(
        render_devices=devices, nvidia=nvidia, encoders={name: name in found for name in wanted}
    )


@dataclass(frozen=True)
class HwTestResult:
    ok: bool
    seconds: float
    message: str


def run_hwaccel_test(hwaccel: str, vaapi_device: str) -> HwTestResult:
    started = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603 – arguments built from validated input
            hwaccel_test_command(hwaccel, vaapi_device),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return HwTestResult(False, time.monotonic() - started, str(exc))
    seconds = time.monotonic() - started
    if result.returncode == 0:
        return HwTestResult(True, seconds, "Funktioniert")
    lines = result.stderr.strip().splitlines()
    return HwTestResult(False, seconds, "\n".join(lines[-4:]) or f"Code {result.returncode}")
