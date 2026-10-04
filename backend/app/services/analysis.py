"""What the media analysis measures, and the ffmpeg commands for it.

* Seek previews ("trickplay"): one small picture every few seconds, put together into
  sheets of 10×10. Only keyframes are decoded, so even a Raspberry Pi gets through an
  hour of video in seconds rather than minutes.
* Loudness: the integrated loudness after EBU R128 (LUFS). The player turns loud videos
  down and quiet ones up a little, so switching videos doesn't startle anyone.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

COLUMNS = 10
ROWS = 10
# Longest side of one preview picture.
THUMB_SIZE = 160
_LOUDNESS = re.compile(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS")


@dataclass(frozen=True)
class Trickplay:
    interval: int  # seconds between two pictures
    width: int
    height: int
    columns: int
    rows: int
    count: int  # pictures in total

    @property
    def sheets(self) -> int:
        return math.ceil(self.count / (self.columns * self.rows))

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def interval_for(duration: float) -> int:
    """Closer pictures for short videos, every 10 seconds for long ones."""
    if duration <= 120:
        return 2
    if duration <= 600:
        return 5
    return 10


def thumb_size(width: int | None, height: int | None) -> tuple[int, int]:
    """Fits into THUMB_SIZE×THUMB_SIZE, even numbers (what the JPEG encoder wants)."""
    if not width or not height:
        width, height = 16, 9

    def even(value: float) -> int:
        return max(2, round(value / 2) * 2)

    if width >= height:
        return THUMB_SIZE, even(THUMB_SIZE * height / width)
    return even(THUMB_SIZE * width / height), THUMB_SIZE


def plan(duration: float, width: int | None, height: int | None) -> Trickplay:
    interval = interval_for(duration)
    w, h = thumb_size(width, height)
    return Trickplay(
        interval=interval,
        width=w,
        height=h,
        columns=COLUMNS,
        rows=ROWS,
        count=max(1, math.ceil(duration / interval)),
    )


def trickplay_args(source: Path, target_dir: Path, trickplay: Trickplay) -> list[str]:
    """ffmpeg arguments (without the binary) writing 1.jpg, 2.jpg, … into target_dir."""
    return [
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-skip_frame",
        "nokey",  # keyframes only: fast, and close enough for a preview
        "-i",
        str(source),
        "-an",
        "-sn",
        "-vf",
        (
            f"fps=1/{trickplay.interval},scale={trickplay.width}:{trickplay.height},"
            f"tile={trickplay.columns}x{trickplay.rows}"
        ),
        "-fps_mode",
        "vfr",
        "-q:v",
        "6",
        "-start_number",
        "1",
        str(target_dir / "%d.jpg"),
    ]


def loudness_args(source: Path) -> list[str]:
    return [
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-i",
        str(source),
        "-vn",
        "-sn",
        "-af",
        "ebur128=framelog=quiet",
        "-f",
        "null",
        "-",
    ]


def parse_loudness(output: str) -> float | None:
    """The integrated loudness from ebur128's summary (the last "I:" line)."""
    found = _LOUDNESS.findall(output)
    if not found:
        return None
    value = float(found[-1])
    # Silence measures as -70 LUFS: nothing to even out.
    return value if value > -70 else None
