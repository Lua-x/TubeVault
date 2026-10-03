"""Converting videos for devices that can't play the original file.

Two ways, both driven by ffmpeg:

* **Remux** – the codecs are fine, only the container isn't (MKV on an iPhone). The streams are
  copied once into an MP4 in the cache; that takes seconds and allows normal seeking.
* **HLS** – the codecs don't work or a smaller quality was chosen. Segments of exactly
  ``SEGMENT_S`` seconds are encoded on demand, so the playlist can be written up front and
  seeking simply starts ffmpeg at another segment.

Everything here is pure (no processes are started), so it can be tested without ffmpeg.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

SEGMENT_S = 6
# Video bitrate (kbit/s) for each output height; picked by the nearest height at or above.
BITRATES = {2160: 16000, 1440: 9000, 1080: 6000, 720: 3000, 480: 1300, 360: 700}
QUALITIES = ("source", "2160", "1440", "1080", "720", "480", "360")
Mode = Literal["software", "vaapi", "vaapi-swdec", "nvenc", "nvenc-swdec"]
# What to try, in order, when the faster variant fails (e.g. the GPU can't decode AV1).
FALLBACKS: dict[str, tuple[Mode, ...]] = {
    "none": ("software",),
    "vaapi": ("vaapi", "vaapi-swdec", "software"),
    "nvenc": ("nvenc", "nvenc-swdec", "software"),
}


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    video_codec: str | None
    width: int | None
    height: int | None
    audio_codec: str | None
    audio_channels: int | None
    format_name: str


def ffmpeg_binary() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_binary() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def parse_probe(data: dict[str, object]) -> MediaInfo:
    streams = data.get("streams")
    fmt = data.get("format")
    if not isinstance(streams, list) or not isinstance(fmt, dict):
        raise ProbeError("Unerwartete Antwort von ffprobe")
    video = next(
        (
            s
            for s in streams
            if isinstance(s, dict)
            and s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next(
        (s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"), None
    )
    try:
        duration = float(fmt.get("duration") or (video or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise ProbeError("Dauer des Videos unbekannt")
    return MediaInfo(
        duration=duration,
        video_codec=(video or {}).get("codec_name"),
        width=(video or {}).get("width"),
        height=(video or {}).get("height"),
        audio_codec=(audio or {}).get("codec_name"),
        audio_channels=(audio or {}).get("channels"),
        format_name=str(fmt.get("format_name") or ""),
    )


@lru_cache(maxsize=256)
def _probe_cached(path: str, size: int, mtime_ns: int) -> MediaInfo:
    del size, mtime_ns  # part of the cache key only
    try:
        result = subprocess.run(  # noqa: S603 – fixed arguments
            [
                ffprobe_binary(),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProbeError(f"ffprobe nicht ausführbar: {exc}") from exc
    if result.returncode != 0:
        raise ProbeError(result.stderr.strip() or "ffprobe fehlgeschlagen")
    return parse_probe(json.loads(result.stdout))


def probe(path: Path) -> MediaInfo:
    stat = path.stat()
    return _probe_cached(str(path), stat.st_size, stat.st_mtime_ns)


# --- codecs -------------------------------------------------------------------------

# ffprobe codec name → RFC 6381 string browsers understand in canPlayType().
_CODEC_STRINGS = {
    "h264": "avc1.640028",
    "hevc": "hvc1.1.6.L120.90",
    "vp9": "vp09.00.40.08",
    "vp8": "vp8",
    "av1": "av01.0.08M.08",
    "aac": "mp4a.40.2",
    "mp3": "mp4a.6b",
    "opus": "opus",
    "vorbis": "vorbis",
    "ac3": "ac-3",
    "eac3": "ec-3",
    "flac": "flac",
}


def codec_string(name: str | None) -> str | None:
    return _CODEC_STRINGS.get(name.lower()) if name else None


def can_copy_into_mp4(info: MediaInfo) -> bool:
    """Whether a lossless remux into MP4 is possible at all."""
    video_ok = info.video_codec in {"h264", "hevc", "vp9", "av1"}
    audio_ok = info.audio_codec in {None, "aac", "mp3", "opus", "ac3", "eac3", "flac"}
    return video_ok and audio_ok


# --- qualities ----------------------------------------------------------------------


def available_heights(source_height: int | None, max_height: int) -> list[int]:
    """Heights offered in the quality menu (below the original, within the limit)."""
    source = source_height or max_height
    return [h for h in sorted(BITRATES, reverse=True) if h <= max_height and h < source]


def target_height(quality: str, source_height: int | None, max_height: int) -> int:
    source = source_height or 1080
    if quality == "source":
        return min(source, max_height)
    try:
        requested = int(quality)
    except ValueError as exc:
        raise ValueError(f"Unbekannte Qualität: {quality}") from exc
    if requested not in BITRATES:
        raise ValueError(f"Unbekannte Qualität: {quality}")
    return min(requested, source, max_height)


def video_bitrate(height: int) -> int:
    for h in sorted(BITRATES):
        if height <= h:
            return BITRATES[h]
    return BITRATES[max(BITRATES)]


# --- HLS ----------------------------------------------------------------------------


def segment_count(duration: float) -> int:
    return max(1, math.ceil(duration / SEGMENT_S - 1e-6))


def hls_playlist(duration: float) -> str:
    """VOD playlist with fixed segments; the files are made when they are requested."""
    count = segment_count(duration)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{SEGMENT_S}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    for index in range(count):
        length = min(SEGMENT_S, duration - index * SEGMENT_S)
        lines += [f"#EXTINF:{max(length, 0.001):.6f},", f"{index}.ts"]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def segment_name(index: int) -> str:
    return f"seg_{index:05d}.ts"


@dataclass(frozen=True)
class HlsJob:
    source: Path
    directory: Path
    start_segment: int
    height: int
    source_height: int | None
    mode: Mode
    vaapi_device: str = "/dev/dri/renderD128"


def _video_args(job: HlsJob) -> tuple[list[str], list[str]]:
    """(arguments before -i, video arguments) for the chosen mode."""
    kbps = video_bitrate(job.height)
    scale = job.source_height is None or job.height < job.source_height
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k", "-bufsize", f"{kbps * 2}k"]
    device = job.vaapi_device
    if job.mode == "vaapi":
        pre = [
            "-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va",
            "-hwaccel", "vaapi", "-hwaccel_device", "va", "-hwaccel_output_format", "vaapi",
        ]  # fmt: skip
        vf = f"scale_vaapi=w=-2:h={job.height}:format=nv12" if scale else "scale_vaapi=format=nv12"
        return pre, ["-vf", vf, "-c:v", "h264_vaapi", "-profile:v", "high", *rate]
    if job.mode == "vaapi-swdec":
        pre = ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
        vf = "format=nv12,hwupload"
        if scale:
            vf += f",scale_vaapi=w=-2:h={job.height}"
        return pre, ["-vf", vf, "-c:v", "h264_vaapi", "-profile:v", "high", *rate]
    nvenc = ["-c:v", "h264_nvenc", "-preset", "p4", "-profile:v", "high", "-rc", "vbr", *rate]
    if job.mode == "nvenc":
        pre = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        vf = f"scale_cuda=-2:{job.height}:format=yuv420p" if scale else "scale_cuda=format=yuv420p"
        return pre, ["-vf", vf, *nvenc]
    if job.mode == "nvenc-swdec":
        vf = f"scale=-2:{job.height},format=yuv420p" if scale else "format=yuv420p"
        return [], ["-vf", vf, *nvenc]
    vf = f"scale=-2:{job.height},format=yuv420p" if scale else "format=yuv420p"
    level = "4.1" if job.height <= 1080 else "5.1"
    software = ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-level:v", level]
    return [], ["-vf", vf, *software, *rate]


def hls_command(job: HlsJob, ffmpeg: str | None = None) -> list[str]:
    """ffmpeg arguments that write segments ``start_segment, start_segment + 1, …``.

    Timestamps restart at 0 for every run (``-ss`` before ``-i``), so forced keyframes and
    segment cuts land exactly on multiples of ``SEGMENT_S``. ``-output_ts_offset`` then moves
    them back to their real position, so segments from different runs fit together.
    """
    start = job.start_segment * SEGMENT_S
    pre, video = _video_args(job)
    return [
        ffmpeg or ffmpeg_binary(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        *pre,
        "-ss", str(start), "-i", str(job.source),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-map_metadata", "-1", "-map_chapters", "-1",
        *video,
        # No B-frames: their reordering delay would make runs overlap by a frame.
        "-bf", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_S})",
        "-c:a", "aac", "-ac", "2", "-b:a", "160k",
        "-output_ts_offset", str(start),
        "-f", "hls", "-hls_time", str(SEGMENT_S), "-hls_list_size", "0",
        "-hls_segment_type", "mpegts", "-hls_flags", "temp_file",
        # Each run restarts the TS continuity counters; flag that so players don't complain.
        "-hls_segment_options", "mpegts_flags=+initial_discontinuity",
        "-start_number", str(job.start_segment),
        "-hls_segment_filename", str(job.directory / "seg_%05d.ts"),
        str(job.directory / "ffmpeg.m3u8"),
    ]  # fmt: skip


def remux_command(
    source: Path, target: Path, video_codec: str | None, ffmpeg: str | None = None
) -> list[str]:
    """Copies video and audio into an MP4 that browsers can seek in (moov atom first)."""
    # Safari only plays HEVC in MP4 when it is tagged hvc1 instead of hev1.
    tag = ["-tag:v", "hvc1"] if video_codec == "hevc" else []
    return [
        ffmpeg or ffmpeg_binary(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-c", "copy", *tag,
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        "-f", "mp4", str(target),
    ]  # fmt: skip


DEVICE_HEIGHTS = (720, 480)
DEVICE_AUDIO_KBPS = 128


def device_command(
    source: Path,
    target: Path,
    height: int,
    source_height: int | None,
    ffmpeg: str | None = None,
) -> list[str]:
    """A compact H.264/AAC MP4 to save on a phone or tablet: plays everywhere, starts
    instantly (moov atom first). Quality-based (CRF) with a cap, so simple videos stay
    small and busy ones don't explode."""
    scale = ["-vf", f"scale=-2:{height}"] if source_height and source_height > height else []
    rate = video_bitrate(min(height, source_height or height))
    return [
        ffmpeg or ffmpeg_binary(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        *scale,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-maxrate", f"{rate}k", "-bufsize", f"{rate * 2}k",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", f"{DEVICE_AUDIO_KBPS}k", "-ac", "2",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        "-f", "mp4", str(target),
    ]  # fmt: skip


def is_aac(audio_codec: str | None) -> bool:
    return (audio_codec or "").lower().startswith(("aac", "mp4a"))


def audio_command(
    source: Path, target: Path, audio_codec: str | None, ffmpeg: str | None = None
) -> list[str]:
    """Only the sound, as M4A: copied when it already is AAC (instant), else converted."""
    codec = (
        ["-c:a", "copy"]
        if is_aac(audio_codec)
        else ["-c:a", "aac", "-b:a", f"{DEVICE_AUDIO_KBPS}k", "-ac", "2"]
    )
    return [
        ffmpeg or ffmpeg_binary(),
        "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        *codec,
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        "-f", "mp4", str(target),
    ]  # fmt: skip


def audio_size_estimate(duration: float) -> int:
    return int((DEVICE_AUDIO_KBPS + 2) * 1000 / 8 * max(duration, 0))


def device_size_estimate(
    duration: float,
    height: int,
    source_height: int | None = None,
    source_size: int | None = None,
    source_codec: str | None = None,
) -> int:
    """Rough size in bytes of a compact copy.

    The cap is the upper limit; most videos stay well below it. The source shows how
    many bits the picture really needs: fewer pixels need fewer bits (though not
    proportionally), and H.264 needs about half again as many as VP9 or AV1.
    """
    if duration <= 0:
        return 0
    target = min(height, source_height or height)
    kbps = video_bitrate(target) * 0.75
    if source_size and source_height:
        source_kbps = max(source_size * 8 / 1000 / duration - DEVICE_AUDIO_KBPS, 0)
        efficient = not (source_codec or "").lower().startswith(("h264", "avc"))
        needed = source_kbps * (target / source_height) ** 1.5 * (1.5 if efficient else 1)
        kbps = min(kbps, max(needed, 150))
    return int((kbps + DEVICE_AUDIO_KBPS) * 1000 / 8 * duration)


def hwaccel_test_command(hwaccel: str, vaapi_device: str, ffmpeg: str | None = None) -> list[str]:
    """Encodes two seconds of a test pattern with the chosen hardware."""
    base = [
        ffmpeg or ffmpeg_binary(),
        "-hide_banner", "-nostdin", "-loglevel", "error",
    ]  # fmt: skip
    source = ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "2"]
    if hwaccel == "vaapi":
        return [
            *base, "-init_hw_device", f"vaapi=va:{vaapi_device}", "-filter_hw_device", "va",
            *source, "-vf", "format=nv12,hwupload,scale_vaapi=w=-2:h=480",
            "-c:v", "h264_vaapi", "-f", "null", "-",
        ]  # fmt: skip
    if hwaccel == "nvenc":
        return [*base, *source, "-vf", "format=yuv420p", "-c:v", "h264_nvenc", "-f", "null", "-"]
    return [*base, *source, "-c:v", "libx264", "-preset", "veryfast", "-f", "null", "-"]
