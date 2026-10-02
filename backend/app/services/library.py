"""File and folder naming inside the media directory (Jellyfin/Plex compatible)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

_REPLACEMENTS = {
    "/": "-",
    "\\": "-",
    ":": " -",
    "|": "-",
    "?": "",
    "*": "",
    '"': "'",
    "<": "",
    ">": "",
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


class UnsafePathError(ValueError):
    pass


def _truncate_bytes(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()


def sanitize_component(name: str, *, max_bytes: int = 150, fallback: str = "Unknown") -> str:
    """Make a string safe as a single path component on Linux, Windows shares and NAS."""
    value = unicodedata.normalize("NFC", name)
    for char, replacement in _REPLACEMENTS.items():
        value = value.replace(char, replacement)
    value = _CONTROL.sub("", value)
    value = _SPACES.sub(" ", value).strip()
    value = _truncate_bytes(value, max_bytes)
    # Windows/SMB do not allow trailing dots or spaces; leading dots would hide the file.
    value = value.strip(" .")
    return value or fallback


def video_basename(title: str, youtube_id: str) -> str:
    return f"{sanitize_component(title, max_bytes=150, fallback='Video')} [{youtube_id}]"


def video_base_path(
    channel_folder: str, upload_date: date | None, title: str, youtube_id: str
) -> Path:
    """`<Channel>/<Year>/<Title> [<id>]` without extension, relative to the media root."""
    year = str(upload_date.year) if upload_date else "Unknown"
    return Path(channel_folder) / year / video_basename(title, youtube_id)


def resolve_media_path(media_dir: Path, relative: str | Path) -> Path:
    """Resolve a stored relative path and make sure it stays inside the media root."""
    root = media_dir.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise UnsafePathError(str(relative))
    return candidate


def relative_to_media(media_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(media_dir.resolve()).as_posix()
