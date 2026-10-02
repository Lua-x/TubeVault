"""Reading channels and playlists: resolving URLs and listing their videos (flat, no download)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.models import SubscriptionKind
from app.services.downloader import ytdlp_logger

log = logging.getLogger(__name__)

CHANNEL_TABS = ("videos", "shorts", "streams")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "[unavailable video]"}


@dataclass(slots=True)
class SourceInfo:
    kind: SubscriptionKind
    youtube_id: str
    title: str
    url: str
    channel_id: str | None = None
    channel_name: str | None = None
    channel_handle: str | None = None
    channel_url: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


@dataclass(slots=True)
class Entry:
    youtube_id: str
    title: str | None = None
    duration_s: int | None = None
    # Approximate for channel listings ("3 weeks ago"); exact after the metadata is read.
    upload_date: date | None = None
    live_status: str | None = None
    is_short: bool = False
    unavailable: bool = False


@dataclass(slots=True)
class Listing:
    source: SourceInfo
    entries: list[Entry] = field(default_factory=list)


class Catalog(Protocol):
    def resolve(self, kind: SubscriptionKind, url: str) -> SourceInfo: ...

    def list_entries(
        self, kind: SubscriptionKind, url: str, *, tabs: list[str], limit: int | None
    ) -> Listing: ...

    def fetch_image(self, url: str) -> bytes | None: ...


def channel_url(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}"


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def _thumbnail(info: dict[str, Any], wanted: str) -> str | None:
    for thumb in info.get("thumbnails") or []:
        if thumb.get("id") == wanted and thumb.get("url"):
            return str(thumb["url"])
    return None


def source_from_info(kind: SubscriptionKind, info: dict[str, Any]) -> SourceInfo:
    channel_id = info.get("channel_id")
    channel_name = info.get("channel") or info.get("uploader")
    handle = info.get("uploader_id")
    handle = handle if isinstance(handle, str) and handle.startswith("@") else None
    if kind is SubscriptionKind.CHANNEL:
        youtube_id = str(channel_id or info.get("id") or "")
        if not youtube_id:
            raise ValueError("Der Kanal konnte nicht erkannt werden.")
        return SourceInfo(
            kind=kind,
            youtube_id=youtube_id,
            title=str(channel_name or youtube_id),
            url=channel_url(youtube_id),
            channel_id=youtube_id,
            channel_name=channel_name,
            channel_handle=handle,
            channel_url=channel_url(youtube_id),
            avatar_url=_thumbnail(info, "avatar_uncropped"),
            banner_url=_thumbnail(info, "banner_uncropped"),
        )
    playlist_id = str(info.get("id") or "")
    if not playlist_id:
        raise ValueError("Die Playlist konnte nicht erkannt werden.")
    return SourceInfo(
        kind=kind,
        youtube_id=playlist_id,
        title=str(info.get("title") or playlist_id),
        url=playlist_url(playlist_id),
        channel_id=channel_id,
        channel_name=channel_name,
        channel_handle=handle,
        channel_url=channel_url(channel_id) if channel_id else None,
    )


def entry_from_info(info: dict[str, Any], *, tab: str | None = None) -> Entry | None:
    youtube_id = info.get("id")
    if not isinstance(youtube_id, str) or not youtube_id:
        return None
    title = info.get("title")
    timestamp = info.get("timestamp")
    upload_date = None
    if isinstance(timestamp, (int, float)):
        upload_date = datetime.fromtimestamp(timestamp, UTC).date()
    elif isinstance(info.get("upload_date"), str) and len(info["upload_date"]) == 8:
        try:
            upload_date = datetime.strptime(info["upload_date"], "%Y%m%d").date()
        except ValueError:
            upload_date = None
    duration = info.get("duration")
    live_status = info.get("live_status")
    if tab == "streams" and live_status is None:
        live_status = "was_live"
    return Entry(
        youtube_id=youtube_id,
        title=title if isinstance(title, str) else None,
        duration_s=int(duration) if isinstance(duration, (int, float)) else None,
        upload_date=upload_date,
        live_status=live_status if isinstance(live_status, str) else None,
        is_short=tab == "shorts" or "/shorts/" in str(info.get("url") or ""),
        unavailable=isinstance(title, str) and title.lower() in UNAVAILABLE_TITLES,
    )


def sort_newest_first(entries: list[Entry]) -> list[Entry]:
    """Stable sort by (approximate) date; entries without a date keep their listing order."""
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda pair: (-(pair[1].upload_date or date.min).toordinal(), pair[0]))
    return [entry for _, entry in indexed]


def _missing_tab(exc: Exception) -> bool:
    message = str(exc).lower()
    return "does not have a" in message and "tab" in message


class YtDlpCatalog:
    def __init__(self, socket_timeout: int = 30) -> None:
        self._socket_timeout = socket_timeout

    def _options(self, limit: int | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "logger": ytdlp_logger(),
            "quiet": True,
            "noprogress": True,
            "extract_flat": "in_playlist",
            "socket_timeout": self._socket_timeout,
            "extractor_retries": 3,
            # Approximate upload dates for flat entries ("3 days ago" → a date).
            "extractor_args": {"youtubetab": {"approximate_date": ["true"]}},
        }
        if limit is not None:
            options["playlistend"] = limit
        return options

    def _extract(self, url: str, limit: int | None) -> dict[str, Any]:
        from yt_dlp import YoutubeDL

        with YoutubeDL(self._options(limit)) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False)
        return info

    def resolve(self, kind: SubscriptionKind, url: str) -> SourceInfo:
        target = f"{url.rstrip('/')}/videos" if kind is SubscriptionKind.CHANNEL else url
        try:
            info = self._extract(target, 1)
        except Exception as exc:
            if kind is SubscriptionKind.CHANNEL and _missing_tab(exc):
                # Channels with only shorts or streams.
                info = self._extract(f"{url.rstrip('/')}/shorts", 1)
            else:
                raise
        return source_from_info(kind, info)

    def list_entries(
        self, kind: SubscriptionKind, url: str, *, tabs: list[str], limit: int | None
    ) -> Listing:
        if kind is SubscriptionKind.PLAYLIST:
            info = self._extract(url, limit)
            items = [e for raw in info.get("entries") or [] if (e := entry_from_info(raw))]
            return Listing(source_from_info(kind, info), sort_newest_first(items))

        source: SourceInfo | None = None
        entries: list[Entry] = []
        for tab in tabs:
            try:
                info = self._extract(f"{url.rstrip('/')}/{tab}", limit)
            except Exception as exc:
                if _missing_tab(exc):
                    log.debug("Kanal %s hat keinen Tab %s", url, tab)
                    continue
                raise
            source = source or source_from_info(kind, info)
            entries += [
                e for raw in info.get("entries") or [] if (e := entry_from_info(raw, tab=tab))
            ]
        if source is None:
            raise ValueError("Der Kanal hat keine Videos.")
        return Listing(source, sort_newest_first(entries))

    def fetch_image(self, url: str) -> bytes | None:
        from yt_dlp import YoutubeDL

        try:
            with YoutubeDL(self._options()) as ydl:
                response = ydl.urlopen(url)
                data: bytes = response.read(MAX_IMAGE_BYTES + 1)
        except Exception as exc:
            log.debug("Bild konnte nicht geladen werden (%s): %s", url, exc)
            return None
        return data if 0 < len(data) <= MAX_IMAGE_BYTES else None
