"""Importing video files that are already on disk: an older yt-dlp archive or own videos.

Files come from the optional import folder (``/import``) or from anywhere below the media
folder that TubeVault doesn't know yet. The YouTube ID is taken from a yt-dlp
``.info.json`` next to the file or from the file name. Files without one are own videos
(camera, phone, …): their folder becomes the channel (see app/services/own_videos.py).
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import LiveContentError
from app.models import Subtitle, Video, VideoStatus
from app.services import nfo, own_videos
from app.services.downloader import Downloader, VideoMetadata, metadata_from_info
from app.services.languages import subtitle_label
from app.services.library import relative_to_media, video_base_path
from app.services.transcode import ProbeError, codec_string, ffmpeg_binary, probe
from app.services.videos import upsert_video, video_file_exists

log = logging.getLogger(__name__)

Root = Literal["import", "media"]
Mode = Literal["move", "copy", "keep"]
Status = Literal["ready", "known"]
Kind = Literal["youtube", "own"]
Source = Literal["info.json", "Dateiname", "Eigenes Video"]

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".m4v", ".mov"}
THUMB_EXTENSIONS = (".jpg", ".jpeg", ".webp", ".png")
MAX_INFO_JSON = 20 * 1024 * 1024
_ID = r"[A-Za-z0-9_-]{11}"
# "Title [ID]" (TubeVault, yt-dlp), "Title (ID)", "Title-ID" (old yt-dlp default), "ID"
_ID_PATTERNS = (
    re.compile(rf"\[({_ID})\]$"),
    re.compile(rf"\(({_ID})\)$"),
    re.compile(rf"(?:^|[-_ ])({_ID})$"),
)


class ImportSkippedError(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    key: str
    root: Root
    relative: str
    size: int
    # For own videos: their fingerprint, "local-…".
    youtube_id: str
    source: Source
    title: str
    status: Status
    kind: Kind = "youtube"


@dataclass
class ScanResult:
    scanned_at: str
    candidates: list[Candidate] = field(default_factory=list)


def read_info_json(file: Path) -> dict[str, Any] | None:
    sidecar = file.with_suffix(".info.json")
    try:
        if not sidecar.is_file() or sidecar.stat().st_size > MAX_INFO_JSON:
            return None
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def id_from_name(stem: str) -> str | None:
    for pattern in _ID_PATTERNS:
        if match := pattern.search(stem.strip()):
            return match.group(1)
    return None


def title_from_name(stem: str, youtube_id: str | None) -> str:
    title = stem
    if youtube_id:
        for pattern in _ID_PATTERNS:
            title = pattern.sub("", title.strip())
    title = re.sub(r"[_]+", " ", title).strip(" -_")
    return title or youtube_id or stem


def detect(file: Path) -> tuple[str | None, Literal["info.json", "Dateiname"] | None, str]:
    """(YouTube ID, where it came from, title)."""
    info = read_info_json(file)
    if info and isinstance(info.get("id"), str) and re.fullmatch(_ID, info["id"]):
        return info["id"], "info.json", str(info.get("title") or file.stem)
    youtube_id = id_from_name(file.stem)
    return youtube_id, "Dateiname" if youtube_id else None, title_from_name(file.stem, youtube_id)


def scan(
    roots: list[tuple[Root, Path]], known_paths: set[str], known_ids: set[str]
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for label, root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Hidden folders (our .tubevault cache, @eaDir on Synology, …) are skipped.
            dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "@")))
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if name.startswith(".") or path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                relative = path.relative_to(root).as_posix()
                if label == "media" and relative in known_paths:
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                youtube_id, found_in, title = detect(path)
                kind: Kind = "youtube"
                source: Source
                if youtube_id is None or found_in is None:
                    try:
                        youtube_id = own_videos.fingerprint(path)
                    except OSError:
                        continue
                    kind, source = "own", "Eigenes Video"
                else:
                    source = found_in
                candidates.append(
                    Candidate(
                        key=f"{label}:{relative}",
                        root=label,
                        relative=relative,
                        size=size,
                        youtube_id=youtube_id,
                        source=source,
                        title=title,
                        status="known" if youtube_id in known_ids else "ready",
                        kind=kind,
                    )
                )
    return candidates


def _transfer(source: Path, target: Path, mode: Mode) -> None:
    if source == target:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "move":
        shutil.move(source, target)
    else:
        shutil.copy2(source, target)


def _ffmpeg(*args: str) -> bool:
    try:
        result = subprocess.run(  # noqa: S603 – fixed binary, paths we chose
            [ffmpeg_binary(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _subtitles(source: Path) -> list[tuple[Path, str]]:
    """`<stem>.<lang>.vtt` / `.srt` next to the file, e.g. `Title [ID].de.vtt`."""
    found: list[tuple[Path, str]] = []
    pattern = f"{glob.escape(source.stem)}.*"
    for path in sorted(source.parent.glob(pattern)):
        if path.suffix.lower() not in (".vtt", ".srt"):
            continue
        lang = path.name[len(source.stem) + 1 : -len(path.suffix)]
        if lang and len(lang) <= 16 and "." not in lang.strip("."):
            found.append((path, lang))
    return found


def _thumbnail(source: Path) -> Path | None:
    for ext in THUMB_EXTENSIONS:
        for candidate in (source.with_suffix(ext), source.parent / f"{source.stem}-thumb{ext}"):
            if candidate.is_file():
                return candidate
    return None


class Importer:
    def __init__(self, media_dir: Path, import_dir: Path, downloader: Downloader) -> None:
        self.media_dir = media_dir
        self.import_dir = import_dir
        self._downloader = downloader
        self._lock = threading.Lock()
        self.last_scan: ScanResult | None = None

    def roots(self) -> list[tuple[Root, Path]]:
        return [("import", self.import_dir), ("media", self.media_dir)]

    def root_path(self, root: Root) -> Path:
        return self.import_dir if root == "import" else self.media_dir

    def run_scan(self, db: Session) -> ScanResult:
        known_paths = {p for p in db.scalars(select(Video.file_path)) if p}
        known_ids = set(
            db.scalars(select(Video.youtube_id).where(Video.status == VideoStatus.READY))
        )
        result = ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            candidates=scan(self.roots(), known_paths, known_ids),
        )
        with self._lock:
            self.last_scan = result
        return result

    def find(self, keys: list[str]) -> list[Candidate]:
        with self._lock:
            scan_result = self.last_scan
        if scan_result is None:
            return []
        wanted = set(keys)
        return [c for c in scan_result.candidates if c.key in wanted]

    def _own_metadata(self, candidate: Candidate, source: Path) -> VideoMetadata:
        """What the file itself tells: title, description and when it was recorded."""
        info = own_videos.embedded_info(source)
        channel_id, channel_name = own_videos.folder_channel(candidate.relative)
        return VideoMetadata(
            youtube_id=candidate.youtube_id,
            title=info.title or candidate.title,
            webpage_url="",
            description=info.description,
            channel_id=channel_id,
            channel_name=channel_name,
            upload_date=info.recorded or own_videos.file_date(source),
        )

    def _metadata(self, candidate: Candidate, source: Path, fetch: bool) -> VideoMetadata:
        url = f"https://www.youtube.com/watch?v={candidate.youtube_id}"
        info = read_info_json(source)
        if info:
            try:
                meta = metadata_from_info(info)
                if meta.youtube_id == candidate.youtube_id:
                    return meta
            except (LiveContentError, ValueError):
                pass
        if fetch:
            try:
                return self._downloader.fetch_metadata(url)
            except Exception as exc:  # deleted or private videos are common in old archives
                log.info("Keine Infos von YouTube für %s: %s", candidate.youtube_id, exc)
        return VideoMetadata(
            youtube_id=candidate.youtube_id, title=candidate.title, webpage_url=url
        )

    def import_one(
        self,
        db: Session,
        candidate: Candidate,
        *,
        mode: Mode,
        fetch_metadata: bool,
        layout: str,
        write_nfo: bool,
        user_id: int | None,
    ) -> Video:
        if mode == "keep" and candidate.root != "media":
            raise ImportSkippedError("Nur Dateien unter /media können liegen bleiben")
        source = self.root_path(candidate.root) / candidate.relative
        if not source.is_file():
            raise ImportSkippedError("Datei nicht mehr vorhanden")
        existing = db.scalar(select(Video).where(Video.youtube_id == candidate.youtube_id))
        if (
            existing is not None
            and existing.status is VideoStatus.READY
            and video_file_exists(self.media_dir, existing)
        ):
            raise ImportSkippedError("Schon in der Bibliothek")

        meta = (
            self._own_metadata(candidate, source)
            if candidate.kind == "own"
            else self._metadata(candidate, source, fetch_metadata)
        )
        video = upsert_video(db, meta, user_id)
        video.manual = True
        folder = video.channel.folder_name if video.channel else "Unknown"
        if mode == "keep":
            target = source
        else:
            base = video_base_path(folder, meta.upload_date, meta.title, meta.youtube_id, layout)
            target = self.media_dir / base.parent / f"{base.name}{source.suffix.lower()}"
            if target.exists() and target != source:
                raise ImportSkippedError(f"Ziel existiert schon: {target.name}")

        # Sidecars are collected before the video moves away from them.
        thumb_source = _thumbnail(source)
        subtitle_sources = _subtitles(source)
        _transfer(source, target, mode)

        thumb_target: Path | None = None
        if thumb_source is not None:
            thumb_target = (
                thumb_source
                if mode == "keep"
                else target.parent / f"{target.stem}-thumb{thumb_source.suffix.lower()}"
            )
            _transfer(thumb_source, thumb_target, mode)

        info = None
        try:
            info = probe(target)
        except (ProbeError, OSError) as exc:
            log.info("ffprobe kann %s nicht lesen: %s", target.name, exc)
        if thumb_target is None:
            generated = target.parent / f"{target.stem}-thumb.jpg"
            position = min(30.0, info.duration * 0.1) if info else 1.0
            if _ffmpeg("-ss", f"{position:.1f}", "-i", str(target), "-frames:v", "1",
                       "-q:v", "3", str(generated)):  # fmt: skip
                thumb_target = generated

        video.subtitles.clear()
        db.flush()
        for sub_source, lang in subtitle_sources:
            sub_target = (
                sub_source
                if mode == "keep" and sub_source.suffix.lower() == ".vtt"
                else target.parent / f"{target.stem}.{lang}.vtt"
            )
            if sub_source.suffix.lower() == ".srt":
                if not _ffmpeg("-i", str(sub_source), str(sub_target)):
                    continue
                if mode == "move":
                    sub_source.unlink(missing_ok=True)
            else:
                _transfer(sub_source, sub_target, mode)
            # Whether YouTube generated them can't be told from the file name.
            video.subtitles.append(
                Subtitle(
                    lang=lang,
                    label=subtitle_label(lang, False),
                    is_auto=False,
                    file_path=relative_to_media(self.media_dir, sub_target),
                )
            )

        video.file_path = relative_to_media(self.media_dir, target)
        video.thumbnail_path = (
            relative_to_media(self.media_dir, thumb_target) if thumb_target else None
        )
        video.filesize = target.stat().st_size
        if info is not None:
            video.width, video.height = info.width, info.height
            video.vcodec = codec_string(info.video_codec) or info.video_codec
            video.acodec = codec_string(info.audio_codec) or info.audio_codec
            if not video.duration_s:
                video.duration_s = round(info.duration)
        video.status = VideoStatus.READY
        video.downloaded_at = datetime.now(UTC)
        db.commit()
        if write_nfo:
            try:
                nfo.write_day_siblings(db, self.media_dir, video, layout)
            except OSError:
                log.warning("NFO für %s fehlt", video.youtube_id, exc_info=True)
        return video
