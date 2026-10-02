"""Validation and normalisation of YouTube video URLs."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

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
                "Playlists und Kanäle lassen sich ab Version 0.2 abonnieren. "
                "Bitte hier die URL eines einzelnen Videos angeben."
            )
        raise InvalidVideoUrlError("In der URL wurde keine gültige Video-ID gefunden.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id
