"""Validation and normalisation of YouTube video URLs."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.models import SubscriptionKind

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PATH_PREFIXES = ("shorts", "live", "embed", "v", "e")


class InvalidVideoUrlError(ValueError):
    pass


def parse_video_url(raw: str) -> tuple[str, str]:
    """Return `(canonical_url, video_id)` or raise InvalidVideoUrlError with a readable message."""
    value = raw.strip()
    if _VIDEO_ID.match(value):
        return f"https://www.youtube.com/watch?v={value}", value
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in YOUTUBE_HOSTS:
        raise InvalidVideoUrlError("Bitte eine YouTube-URL angeben.")

    video_id: str | None = None
    parts = [p for p in parsed.path.split("/") if p]
    if host.endswith("youtu.be") and parts:
        video_id = parts[0]
    elif parts[:1] == ["watch"] or not parts:
        values = parse_qs(parsed.query).get("v")
        video_id = values[0] if values else None
    elif len(parts) >= 2 and parts[0] in _PATH_PREFIXES:
        video_id = parts[1]

    if not video_id or not _VIDEO_ID.match(video_id):
        if (
            "list" in parse_qs(parsed.query)
            or parts[:1] in (["playlist"], ["channel"], ["c"])
            or (parts and parts[0].startswith("@"))
        ):
            raise InvalidVideoUrlError(
                "Das ist eine Playlist oder ein Kanal. Abonniere sie unter „Abos“ – "
                "hier geht nur die URL eines einzelnen Videos."
            )
        raise InvalidVideoUrlError("In der URL wurde keine gültige Video-ID gefunden.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_PLAYLIST_ID = re.compile(r"^(PL|UU|OL|FL|LL|RD|UL|PU)[A-Za-z0-9_-]{8,}$")
_HANDLE = re.compile(r"^@[\w.\-·]{2,100}$")
_CHANNEL_TABS = {"videos", "shorts", "streams", "featured", "playlists", "community", "about"}


def parse_source_url(raw: str) -> tuple[SubscriptionKind, str]:
    """Return `(kind, url)` for a channel or playlist, or raise InvalidVideoUrlError."""
    value = raw.strip()
    if _HANDLE.match(value):
        return SubscriptionKind.CHANNEL, f"https://www.youtube.com/{value}"
    if _CHANNEL_ID.match(value):
        return SubscriptionKind.CHANNEL, f"https://www.youtube.com/channel/{value}"
    if _PLAYLIST_ID.match(value):
        return SubscriptionKind.PLAYLIST, f"https://www.youtube.com/playlist?list={value}"
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in YOUTUBE_HOSTS:
        raise InvalidVideoUrlError(
            "Bitte die URL eines YouTube-Kanals oder einer Playlist angeben."
        )

    lists = parse_qs(parsed.query).get("list")
    playlist = lists[0] if lists else None
    if playlist and re.fullmatch(r"[A-Za-z0-9_-]{10,}", playlist):
        return SubscriptionKind.PLAYLIST, f"https://www.youtube.com/playlist?list={playlist}"

    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[-1].lower() in _CHANNEL_TABS:
        parts = parts[:-1]
    if len(parts) == 1 and _HANDLE.match(parts[0]):
        return SubscriptionKind.CHANNEL, f"https://www.youtube.com/{parts[0]}"
    if len(parts) == 2 and parts[0] == "channel" and _CHANNEL_ID.match(parts[1]):
        return SubscriptionKind.CHANNEL, f"https://www.youtube.com/channel/{parts[1]}"
    if len(parts) == 2 and parts[0] in ("c", "user"):
        return SubscriptionKind.CHANNEL, f"https://www.youtube.com/{parts[0]}/{parts[1]}"
    raise InvalidVideoUrlError(
        "Das ist weder ein Kanal noch eine Playlist. Beispiele: "
        "https://www.youtube.com/@kanal oder https://www.youtube.com/playlist?list=…"
    )
