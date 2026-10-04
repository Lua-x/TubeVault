"""Own videos – files that come from a camera or a phone rather than from YouTube.

They live in the library like everything else, so the player, the TV view, DLNA,
playlists and the profiles work as usual. Their ID starts with ``local-`` (a YouTube ID
has exactly 11 characters, so the two never collide), and the folder they came from
becomes their "channel": ``/import/Urlaub 2024/Strand.mp4`` lands in "Urlaub 2024".
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

from app.models.video import LOCAL_PREFIX
from app.services.transcode import ffprobe_binary

DEFAULT_FOLDER = "Eigene Videos"
_SAMPLE = 64 * 1024


def is_local(youtube_id: str | None) -> bool:
    return bool(youtube_id) and str(youtube_id).startswith(LOCAL_PREFIX)


def fingerprint(path: Path) -> str:
    """The same file gets the same ID – also as a copy, or after the database was lost.

    Size plus the first and the last 64 KiB: enough to tell videos apart, and quick even
    for big files on a slow NAS.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        size = file.seek(0, 2)
        digest.update(str(size).encode())
        file.seek(0)
        digest.update(file.read(_SAMPLE))
        if size > _SAMPLE:
            file.seek(max(_SAMPLE, size - _SAMPLE))
            digest.update(file.read(_SAMPLE))
    return f"{LOCAL_PREFIX}{digest.hexdigest()[:16]}"


def folder_channel(relative: str) -> tuple[str, str]:
    """(channel ID, name) for a file: its top folder below the import root."""
    parts = PurePosixPath(relative).parts
    name = parts[0] if len(parts) > 1 else DEFAULT_FOLDER
    key = hashlib.sha256(name.casefold().encode()).hexdigest()[:16]
    return f"{LOCAL_PREFIX}{key}", name


@dataclass(frozen=True)
class EmbeddedInfo:
    title: str | None = None
    description: str | None = None
    recorded: date | None = None


def _tag(tags: dict[str, object], *names: str) -> str | None:
    lowered = {str(k).lower(): v for k, v in tags.items()}
    for name in names:
        value = lowered.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_tags(tags: dict[str, object]) -> EmbeddedInfo:
    recorded = None
    created = _tag(tags, "creation_time", "date", "com.apple.quicktime.creationdate")
    if created:
        try:
            recorded = datetime.fromisoformat(created.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                recorded = date.fromisoformat(created[:10])
            except ValueError:
                recorded = None
    return EmbeddedInfo(
        title=_tag(tags, "title", "com.apple.quicktime.title"),
        description=_tag(tags, "description", "comment", "synopsis"),
        recorded=recorded,
    )


def embedded_info(path: Path) -> EmbeddedInfo:
    """Title, description and recording date written into the file, as far as present."""
    try:
        result = subprocess.run(  # noqa: S603 – fixed binary, a path we chose
            [
                ffprobe_binary(),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_entries",
                "format_tags",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return EmbeddedInfo()
    tags = (data.get("format") or {}).get("tags") or {}
    return parse_tags(tags) if isinstance(tags, dict) else EmbeddedInfo()


def file_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
