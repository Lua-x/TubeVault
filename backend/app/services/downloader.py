"""yt-dlp integration: metadata extraction and downloading.

The `Downloader` protocol keeps the queue independent of yt-dlp, so tests (and future
backends) can plug in their own implementation.
"""

from __future__ import annotations

import copy
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from app.core.errors import LiveContentError
from app.services.app_settings import DownloadOptions

log = logging.getLogger(__name__)
ytdlp_log = logging.getLogger("yt_dlp")

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".m4v", ".mov")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class DownloadCancelledError(Exception):
    """Raised from inside a progress hook to abort a running download."""


@dataclass(slots=True)
class VideoMetadata:
    youtube_id: str
    title: str
    webpage_url: str
    description: str | None = None
    channel_id: str | None = None
    channel_name: str | None = None
    channel_handle: str | None = None
    channel_url: str | None = None
    upload_date: date | None = None
    duration_s: int | None = None
    view_count: int | None = None
    is_short: bool = False
    was_live: bool = False
    chapters: list[dict[str, Any]] = field(default_factory=list)
    # The raw yt-dlp info dict, reused for the download so YouTube is only asked once.
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class DownloadProgress:
    stage: Literal["downloading", "postprocessing"]
    progress: float
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None


@dataclass(slots=True)
class SubtitleFile:
    lang: str
    is_auto: bool
    path: Path


@dataclass(slots=True)
class DownloadResult:
    file_path: Path
    thumbnail_path: Path | None = None
    subtitles: list[SubtitleFile] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    vcodec: str | None = None
    acodec: str | None = None
    # Set when SponsorBlock segments were cut out: chapters and duration changed.
    sponsorblock_cut: bool = False
    chapters: list[dict[str, Any]] | None = None
    duration_s: int | None = None


@dataclass(slots=True)
class CommentData:
    youtube_id: str
    parent_id: str | None  # None for top-level comments
    author: str
    text: str
    like_count: int | None = None
    published_at: datetime | None = None
    author_is_uploader: bool = False
    author_is_verified: bool = False
    is_pinned: bool = False
    is_favorited: bool = False


@dataclass(slots=True)
class CommentsResult:
    comments: list[CommentData]
    total: int | None = None  # how many comments YouTube counts for the video


ProgressCallback = Callable[[DownloadProgress], None]
CancelCheck = Callable[[], bool]


class Downloader(Protocol):
    def fetch_metadata(self, url: str) -> VideoMetadata: ...

    def download(
        self,
        meta: VideoMetadata,
        *,
        media_dir: Path,
        relative_base: Path,
        temp_dir: Path,
        options: DownloadOptions,
        on_progress: ProgressCallback,
        is_cancelled: CancelCheck,
    ) -> DownloadResult: ...

    def fetch_comments(self, url: str, limit: int) -> CommentsResult: ...


# --- helpers ------------------------------------------------------------------


def build_format(options: DownloadOptions) -> tuple[str, list[str]]:
    """Format selector and sort order for yt-dlp – the same approach as Pinchflat.

    Resolution comes first: `res:N` takes the best resolution up to N, measured on the
    shorter side so portrait videos (Shorts) count right, and the smallest larger one only
    if nothing fits. H.264/AAC is only preferred between formats of that resolution: YouTube
    offers H.264 up to 1080p, above that only VP9/AV1 – and those are taken then, instead
    of dropping to 1080p. Nothing is re-encoded; the streams are only put into one file.
    """
    sort = [f"res:{options.max_height}" if options.max_height else "res"]
    if options.prefer_h264:
        sort.append("+codec:avc:m4a")
    return "bv*+ba/b", sort


def _escape_template(value: str) -> str:
    return value.replace("%", "%%")


def _parse_upload_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 8:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_chapters(raw: Any) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for chapter in raw or []:
        try:
            start = float(chapter["start_time"])
            end = float(chapter.get("end_time") or start)
        except (KeyError, TypeError, ValueError):
            continue
        title = str(chapter.get("title") or "").strip() or f"Kapitel {len(chapters) + 1}"
        chapters.append({"start": start, "end": end, "title": title})
    return chapters


def _base_lang(code: str) -> str:
    return code.removesuffix("-orig").split("-")[0].lower()


def pick_subtitles(raw: dict[str, Any], options: DownloadOptions) -> dict[str, bool]:
    """Choose which subtitle tracks to fetch: `{yt-dlp language key: is_auto}`.

    Manual subtitles win. Automatic captions are only taken in the video's original
    language (YouTube's machine translations are poor and heavily rate-limited).
    """
    wanted = set(options.subtitle_languages)
    chosen: dict[str, bool] = {}
    covered: set[str] = set()
    if options.subtitles:
        for key in raw.get("subtitles") or {}:
            base = _base_lang(key)
            if key != "live_chat" and base in wanted and base not in covered:
                chosen[key] = False
                covered.add(base)
    if options.auto_subtitles:
        auto = raw.get("automatic_captions") or {}
        originals = [key for key in auto if key.endswith("-orig")]
        if not originals:
            language = raw.get("language")
            originals = [language] if isinstance(language, str) and language in auto else []
        for key in originals:
            base = _base_lang(key)
            if base in wanted and base not in covered:
                chosen[key] = True
                covered.add(base)
    return chosen


def metadata_from_info(info: dict[str, Any]) -> VideoMetadata:
    live_status = info.get("live_status")
    if live_status in ("is_live", "is_upcoming", "post_live"):
        messages = {
            "is_live": "Der Livestream läuft noch – Download ist erst nach dem Ende möglich.",
            "is_upcoming": "Livestream oder Premiere hat noch nicht begonnen.",
            "post_live": "Der Livestream ist gerade zu Ende und wird von YouTube noch verarbeitet.",
        }
        raise LiveContentError(messages[live_status])

    youtube_id = str(info.get("id") or "")
    if not youtube_id:
        raise ValueError("yt-dlp lieferte keine Video-ID.")
    handle = info.get("uploader_id")
    duration = info.get("duration")
    return VideoMetadata(
        youtube_id=youtube_id,
        title=str(info.get("title") or youtube_id),
        webpage_url=str(info.get("webpage_url") or info.get("original_url") or ""),
        description=info.get("description"),
        channel_id=info.get("channel_id"),
        channel_name=info.get("channel") or info.get("uploader"),
        channel_handle=handle if isinstance(handle, str) and handle.startswith("@") else None,
        channel_url=info.get("channel_url") or info.get("uploader_url"),
        upload_date=_parse_upload_date(info.get("upload_date")),
        duration_s=int(duration) if isinstance(duration, (int, float)) else None,
        view_count=info.get("view_count"),
        is_short=info.get("media_type") == "short" or "/shorts/" in str(info.get("original_url")),
        was_live=live_status == "was_live",
        chapters=_parse_chapters(info.get("chapters")),
        raw=info,
    )


def comments_from_info(info: dict[str, Any]) -> CommentsResult:
    comments: list[CommentData] = []
    for raw in info.get("comments") or []:
        comment_id = str(raw.get("id") or "")
        if not comment_id:
            continue
        parent = raw.get("parent")
        timestamp = raw.get("timestamp")
        likes = raw.get("like_count")
        comments.append(
            CommentData(
                youtube_id=comment_id,
                parent_id=None if parent in (None, "root") else str(parent),
                author=str(raw.get("author") or "").strip() or "Unbekannt",
                text=str(raw.get("text") or ""),
                like_count=int(likes) if isinstance(likes, (int, float)) else None,
                published_at=(
                    datetime.fromtimestamp(timestamp, UTC)
                    if isinstance(timestamp, (int, float))
                    else None
                ),
                author_is_uploader=bool(raw.get("author_is_uploader")),
                author_is_verified=bool(raw.get("author_is_verified")),
                is_pinned=bool(raw.get("is_pinned")),
                is_favorited=bool(raw.get("is_favorited")),
            )
        )
    total = info.get("comment_count")
    return CommentsResult(comments, int(total) if isinstance(total, (int, float)) else None)


class _YtDlpLogger:
    """Routes yt-dlp output into our logging (debug chatter stays at DEBUG)."""

    def debug(self, msg: str) -> None:
        ytdlp_log.debug(msg.removeprefix("[debug] "))

    def info(self, msg: str) -> None:
        ytdlp_log.debug(msg)

    def warning(self, msg: str) -> None:
        ytdlp_log.warning(msg)

    def error(self, msg: str) -> None:
        ytdlp_log.warning(msg)


def ytdlp_logger() -> _YtDlpLogger:
    return _YtDlpLogger()


class _ProgressTracker:
    """Combines the separate video and audio downloads into one overall progress."""

    def __init__(self, info: dict[str, Any], callback: ProgressCallback, cancel: CancelCheck):
        self._callback = callback
        self._cancel = cancel
        self._done: dict[str, int] = {}
        self._totals: dict[str, int] = {}
        for fmt in info.get("requested_formats") or [info]:
            size = fmt.get("filesize") or fmt.get("filesize_approx")
            if fmt.get("format_id") and size:
                self._totals[str(fmt["format_id"])] = int(size)

    def hook(self, d: dict[str, Any]) -> None:
        if self._cancel():
            raise DownloadCancelledError
        if d.get("status") not in ("downloading", "finished"):
            return
        format_id = str((d.get("info_dict") or {}).get("format_id") or "main")
        downloaded = int(d.get("downloaded_bytes") or 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            self._totals[format_id] = int(total)
        if d.get("status") == "finished":
            downloaded = self._totals.get(format_id, downloaded)
        self._done[format_id] = downloaded

        total_all = sum(self._totals.values()) or None
        done_all = sum(self._done.values())
        progress = min(done_all / total_all, 0.999) if total_all else 0.0
        self._callback(
            DownloadProgress(
                stage="downloading",
                progress=progress,
                downloaded_bytes=done_all,
                total_bytes=total_all,
                speed=d.get("speed"),
                eta=int(d["eta"]) if d.get("eta") is not None else None,
            )
        )

    def postprocessor_hook(self, d: dict[str, Any]) -> None:
        if self._cancel():
            raise DownloadCancelledError
        if d.get("status") == "started":
            self._callback(DownloadProgress(stage="postprocessing", progress=0.999))


# --- the real thing -------------------------------------------------------------


class YtDlpDownloader:
    def __init__(self, socket_timeout: int = 30) -> None:
        self._socket_timeout = socket_timeout

    def _base_options(self) -> dict[str, Any]:
        return {
            "logger": ytdlp_logger(),
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": self._socket_timeout,
            "retries": 5,
            "fragment_retries": 10,
            "extractor_retries": 3,
            "ignoreerrors": False,
        }

    def fetch_metadata(self, url: str) -> VideoMetadata:
        from yt_dlp import YoutubeDL

        with YoutubeDL(self._base_options()) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False, process=False)
            for _ in range(3):
                if info.get("_type") not in ("url", "url_transparent"):
                    break
                info = ydl.extract_info(info["url"], download=False, process=False)
            if info.get("_type") == "playlist":
                raise ValueError(
                    "Das ist eine Playlist oder ein Kanal. "
                    "Bitte die URL eines einzelnen Videos verwenden."
                )
            return metadata_from_info(info)

    def download(
        self,
        meta: VideoMetadata,
        *,
        media_dir: Path,
        relative_base: Path,
        temp_dir: Path,
        options: DownloadOptions,
        on_progress: ProgressCallback,
        is_cancelled: CancelCheck,
    ) -> DownloadResult:
        from yt_dlp import YoutubeDL

        base = _escape_template(relative_base.as_posix())
        selector, sort = build_format(options)
        tracker = _ProgressTracker(meta.raw, on_progress, is_cancelled)
        temp_dir.mkdir(parents=True, exist_ok=True)

        opts = self._base_options() | {
            "format": selector,
            "format_sort": sort,
            "merge_output_format": options.container,
            "paths": {"home": str(media_dir), "temp": str(temp_dir)},
            "outtmpl": {
                "default": f"{base}.%(ext)s",
                "thumbnail": f"{base}-thumb.%(ext)s",
            },
            "writethumbnail": True,
            "continuedl": True,
            "progress_hooks": [tracker.hook],
            "postprocessor_hooks": [tracker.postprocessor_hook],
            "postprocessors": self._postprocessors(options),
        }
        with YoutubeDL(opts) as ydl:
            info: dict[str, Any] = ydl.process_ie_result(copy.deepcopy(meta.raw), download=True)

        file_path = self._find_media_file(info, media_dir, relative_base)
        cut = options.sponsorblock_mode == "cut" and bool(info.get("sponsorblock_chapters"))
        selected = (info.get("requested_downloads") or [info])[0]
        result = DownloadResult(
            file_path=file_path,
            thumbnail_path=self._find_thumbnail(media_dir, relative_base),
            width=selected.get("width") or info.get("width"),
            height=selected.get("height") or info.get("height"),
            vcodec=selected.get("vcodec") or info.get("vcodec"),
            acodec=selected.get("acodec") or info.get("acodec"),
            sponsorblock_cut=cut,
            chapters=_parse_chapters(info.get("chapters")) if cut else None,
            duration_s=int(info["duration"]) if cut and info.get("duration") else None,
        )
        if not is_cancelled():
            result.subtitles = self._download_subtitles(meta, media_dir, relative_base, options)
        return result

    def fetch_comments(self, url: str, limit: int) -> CommentsResult:
        """Top comments with up to 10 replies each – a separate request, after the video."""
        from yt_dlp import YoutubeDL

        opts = self._base_options() | {
            "skip_download": True,
            "getcomments": True,
            "extractor_args": {
                "youtube": {
                    # total, top-level, replies, replies per thread
                    "max_comments": [str(limit), "all", "all", "10"],
                    "comment_sort": ["top"],
                }
            },
        }
        with YoutubeDL(opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False)
        return comments_from_info(info)

    @staticmethod
    def _postprocessors(options: DownloadOptions) -> list[dict[str, Any]]:
        cut = options.sponsorblock_mode == "cut" and options.sponsorblock_categories
        categories = list(options.sponsorblock_categories)
        postprocessors: list[dict[str, Any]] = []
        if cut:
            postprocessors.append(
                {"key": "SponsorBlock", "categories": categories, "when": "after_filter"}
            )
        postprocessors += [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "FFmpegVideoRemuxer", "preferedformat": options.container},
        ]
        if cut:
            postprocessors.append({"key": "ModifyChapters", "remove_sponsor_segments": categories})
        postprocessors.append(
            {
                "key": "FFmpegMetadata",
                "add_chapters": True,
                "add_metadata": True,
                "add_infojson": False,
            }
        )
        return postprocessors

    def _download_subtitles(
        self, meta: VideoMetadata, media_dir: Path, relative_base: Path, options: DownloadOptions
    ) -> list[SubtitleFile]:
        """Separate pass, so a failing subtitle (often a 429) never fails the video."""
        from yt_dlp import YoutubeDL

        chosen = pick_subtitles(meta.raw, options)
        if not chosen:
            return []
        manual = [key for key, auto in chosen.items() if not auto]
        auto = [key for key, auto in chosen.items() if auto]
        base = _escape_template(relative_base.as_posix())
        opts = self._base_options() | {
            "skip_download": True,
            "ignoreerrors": True,
            "writesubtitles": bool(manual),
            "writeautomaticsub": bool(auto),
            "subtitleslangs": list(chosen),
            "subtitlesformat": "vtt/best",
            "paths": {"home": str(media_dir)},
            "outtmpl": {"default": f"{base}.%(ext)s", "subtitle": f"{base}.%(ext)s"},
            "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "vtt"}],
        }
        try:
            with YoutubeDL(opts) as ydl:
                ydl.process_ie_result(copy.deepcopy(meta.raw), download=True)
        except Exception as exc:
            log.warning("Untertitel für %s konnten nicht geladen werden: %s", meta.youtube_id, exc)

        files: list[SubtitleFile] = []
        target_dir = media_dir / relative_base.parent
        for key, is_auto in chosen.items():
            source = target_dir / f"{relative_base.name}.{key}.vtt"
            if not source.exists():
                continue
            lang = _base_lang(key)
            # Jellyfin/Plex read `<name>.<lang>.vtt`; drop YouTube's "-orig" suffix.
            target = target_dir / f"{relative_base.name}.{lang}.vtt"
            if source != target:
                source.replace(target)
            files.append(SubtitleFile(lang=lang, is_auto=is_auto, path=target))
        return files

    @staticmethod
    def _find_media_file(info: dict[str, Any], media_dir: Path, relative_base: Path) -> Path:
        for download in info.get("requested_downloads") or []:
            path = download.get("filepath")
            if path and Path(path).exists():
                return Path(path)
        target_dir = media_dir / relative_base.parent
        for ext in VIDEO_EXTENSIONS:
            candidate = target_dir / f"{relative_base.name}{ext}"
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Download beendet, aber keine Videodatei gefunden.")

    @staticmethod
    def _find_thumbnail(media_dir: Path, relative_base: Path) -> Path | None:
        target_dir = media_dir / relative_base.parent
        for ext in IMAGE_EXTENSIONS:
            candidate = target_dir / f"{relative_base.name}-thumb{ext}"
            if candidate.exists():
                return candidate
        return None


def cleanup_temp(temp_dir: Path) -> None:
    shutil.rmtree(temp_dir, ignore_errors=True)
