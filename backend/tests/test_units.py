from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import LiveContentError, classify_error, is_retryable, retry_delay
from app.models import ErrorKind
from app.routers.media import chapters_to_vtt
from app.services.app_settings import DownloadOptions
from app.services.downloader import build_format, metadata_from_info, pick_subtitles
from app.services.library import (
    UnsafePathError,
    resolve_media_path,
    sanitize_component,
    video_base_path,
)
from app.services.youtube_urls import InvalidVideoUrlError, parse_video_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AC/DC: Live?", "AC-DC - Live"),
        ("  lots   of   space  ", "lots of space"),
        ("...hidden.", "hidden"),
        ('Say "hi" <now>', "Say 'hi' now"),
        ("", "Unknown"),
        ("a\x00b\x1fc", "abc"),
    ],
)
def test_sanitize_component(raw: str, expected: str) -> None:
    assert sanitize_component(raw) == expected


def test_sanitize_truncates_on_utf8_boundary() -> None:
    value = sanitize_component("ä" * 200, max_bytes=21)
    assert value == "ä" * 10
    assert len(value.encode()) <= 21


def test_video_base_path() -> None:
    path = video_base_path("Kanal", date(2023, 1, 2), "Mr. Titel", "abcdefghijk")
    assert path == Path("Kanal/2023/Mr. Titel [abcdefghijk]")
    assert video_base_path("Kanal", None, "T", "x").parts[1] == "Unknown"


def test_resolve_media_path_blocks_traversal(tmp_path: Path) -> None:
    assert resolve_media_path(tmp_path, "a/b.mp4") == (tmp_path / "a/b.mp4").resolve()
    with pytest.raises(UnsafePathError):
        resolve_media_path(tmp_path, "../etc/passwd")
    with pytest.raises(UnsafePathError):
        resolve_media_path(tmp_path, "/etc/passwd")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=42",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "www.youtube.com/embed/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
    ],
)
def test_parse_video_url(url: str) -> None:
    assert parse_video_url(url) == ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/watch?v=short",
        "javascript:alert(1)",
    ],
)
def test_parse_video_url_rejects(url: str) -> None:
    with pytest.raises(InvalidVideoUrlError):
        parse_video_url(url)


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        (
            "ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
            ErrorKind.RATE_LIMITED,
        ),
        ("Sign in to confirm you're not a bot", ErrorKind.RATE_LIMITED),
        ("ERROR: [youtube] x: Video unavailable", ErrorKind.UNAVAILABLE),
        ("ERROR: [youtube] x: Private video. Sign in", ErrorKind.UNAVAILABLE),
        ("Unable to download webpage: <urlopen error timed out>", ErrorKind.NETWORK),
        ("ERROR: [youtube] x: Premieres in 3 hours", ErrorKind.LIVE),
        ("Something odd happened", ErrorKind.UNKNOWN),
    ],
)
def test_classify_error(message: str, kind: ErrorKind) -> None:
    assert classify_error(Exception(message)) is kind


def test_retry_policy() -> None:
    assert classify_error(LiveContentError("läuft")) is ErrorKind.LIVE
    assert classify_error(ConnectionResetError()) is ErrorKind.NETWORK
    assert not is_retryable(ErrorKind.UNAVAILABLE)
    assert is_retryable(ErrorKind.NETWORK)
    assert retry_delay(ErrorKind.NETWORK, 1).total_seconds() == 30
    assert retry_delay(ErrorKind.NETWORK, 3).total_seconds() == 120
    assert retry_delay(ErrorKind.NETWORK, 20).total_seconds() == 3600
    assert retry_delay(ErrorKind.RATE_LIMITED, 1).total_seconds() == 900


def _yt_format(fid: str, vcodec: str, width: int | None, height: int | None, tbr: int) -> Any:
    ext = "webm" if vcodec in ("vp9", "opus") else ("m4a" if vcodec == "none" else "mp4")
    acodec = {"opus": "opus"}.get(vcodec, "mp4a.40.2" if vcodec == "none" else "none")
    fmt = {
        "format_id": fid,
        "ext": ext,
        "vcodec": "none" if vcodec == "opus" else vcodec,
        "acodec": acodec,
        "tbr": tbr,
        "url": f"https://example.invalid/{fid}",
        "protocol": "https",
    }
    if height:
        fmt |= {"width": width, "height": height}
    return fmt


# What YouTube offers for a 4K video: H.264 only up to 1080p, above that VP9 and AV1.
LANDSCAPE = [
    _yt_format("140", "none", None, None, 129),
    _yt_format("251", "opus", None, None, 135),
    _yt_format("137", "avc1.640028", 1920, 1080, 4400),
    _yt_format("248", "vp9", 1920, 1080, 2700),
    _yt_format("399", "av01.0.08M.08", 1920, 1080, 2100),
    _yt_format("271", "vp9", 2560, 1440, 9000),
    _yt_format("313", "vp9", 3840, 2160, 18000),
    _yt_format("401", "av01.0.13M.08", 3840, 2160, 13500),
]
# A Short: portrait, so "1080p" is 1080 wide and 1920 high.
PORTRAIT = [
    _yt_format("140", "none", None, None, 129),
    _yt_format("135", "avc1.4d401f", 480, 854, 600),
    _yt_format("136", "avc1.4d401f", 720, 1280, 1200),
    _yt_format("137", "avc1.640028", 1080, 1920, 2500),
]


# Right after an upload: only small H.264 versions (one of them with sound) and VP9 1080p.
FRESH = [
    _yt_format("140", "none", None, None, 129),
    _yt_format("251", "opus", None, None, 135),
    {
        "format_id": "18",
        "ext": "mp4",
        "vcodec": "avc1.42001E",
        "acodec": "mp4a.40.2",
        "width": 640,
        "height": 360,
        "tbr": 500,
        "url": "https://example.invalid/18",
        "protocol": "https",
    },
    _yt_format("136", "avc1.4d401f", 1280, 720, 1500),
    _yt_format("248", "vp9", 1920, 1080, 2700),
]


def _picked(formats: list[Any], **options: Any) -> tuple[str, int | None]:
    return _choose(formats, *build_format(DownloadOptions(**options)))


def _choose(formats: list[Any], selector: str, sort: list[str]) -> tuple[str, int | None]:
    """The format yt-dlp itself picks for these options – nothing is downloaded."""
    from yt_dlp import YoutubeDL

    info = {
        "id": "x",
        "title": "x",
        "formats": [dict(f) for f in formats],
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://youtu.be/x",
    }
    params = {"quiet": True, "format": selector, "format_sort": sort, "simulate": True}
    with YoutubeDL(params) as ydl:  # type: ignore[arg-type]
        chosen = ydl.process_ie_result(info, download=False)
    return chosen["format_id"], chosen.get("height")


def test_format_choice_like_pinchflat() -> None:
    """Resolution first; H.264 only between formats of the same resolution."""
    assert _picked(LANDSCAPE, max_height=1080, prefer_h264=True) == ("137+140", 1080)
    # 4K wanted: the 4K stream, even with H.264 preferred (YouTube has none above 1080p).
    assert _picked(LANDSCAPE, max_height=2160, prefer_h264=True) == ("313+140", 2160)
    assert _picked(LANDSCAPE, max_height=None, prefer_h264=True) == ("313+140", 2160)
    assert _picked(LANDSCAPE, max_height=1440, prefer_h264=True) == ("271+140", 1440)
    # Without the preference: the most efficient codec and the better audio.
    assert _picked(LANDSCAPE, max_height=2160, prefer_h264=False) == ("401+251", 2160)
    # Shorts count by their shorter side – full 1080x1920, not a small fallback.
    assert _picked(PORTRAIT, max_height=1080, prefer_h264=True) == ("137+140", 1920)
    assert _picked(PORTRAIT, max_height=720, prefer_h264=True) == ("136+140", 1280)
    # Nothing small enough: the smallest there is instead of failing.
    assert _picked(LANDSCAPE, max_height=360, prefer_h264=True) == ("137+140", 1080)


# Pinchflat's media profiles, and what its QualityOptionBuilder hands yt-dlp for them
# (with its default codec preferences, avc and m4a).
PINCHFLAT_RESOLUTIONS = (4320, 2160, 1440, 1080, 720, 480, 360)


def _pinchflat(formats: list[Any], resolution: int) -> tuple[str, int | None]:
    return _choose(formats, "bestvideo*+bestaudio/best", [f"res:{resolution}", "+codec:avc:m4a"])


@pytest.mark.parametrize("formats", [LANDSCAPE, PORTRAIT, FRESH], ids=["4k", "short", "fresh"])
def test_same_choice_as_pinchflat(formats: list[Any]) -> None:
    """Every Pinchflat profile has a TubeVault setting that takes exactly the same streams –
    so the same file, the same size. Pinchflat's 8K profile is "Beste verfügbare"."""
    for resolution in PINCHFLAT_RESOLUTIONS:
        limit = None if resolution == 4320 else resolution
        assert _picked(formats, max_height=limit) == _pinchflat(formats, resolution), resolution


def test_best_quality_is_the_default() -> None:
    assert DownloadOptions().max_height is None
    assert _picked(LANDSCAPE) == ("313+140", 2160)


def test_pick_subtitles_prefers_manual_and_original_auto() -> None:
    raw = {
        "subtitles": {"en": [{}], "fr": [{}], "live_chat": [{}]},
        "automatic_captions": {"de": [{}], "en": [{}], "en-orig": [{}], "es": [{}]},
    }
    options = DownloadOptions(subtitle_languages=["de", "en"])
    assert pick_subtitles(raw, options) == {"en": False}

    raw_de = {"subtitles": {}, "automatic_captions": {"de-orig": [{}], "de": [{}], "en": [{}]}}
    assert pick_subtitles(raw_de, options) == {"de-orig": True}
    assert pick_subtitles(raw_de, DownloadOptions(auto_subtitles=False)) == {}


def test_metadata_from_info() -> None:
    meta = metadata_from_info(
        {
            "id": "abcdefghijk",
            "title": "Titel",
            "channel_id": "UC1",
            "channel": "Kanal",
            "uploader_id": "@kanal",
            "upload_date": "20240131",
            "duration": 61.5,
            "media_type": "short",
            "live_status": "was_live",
            "chapters": [{"start_time": 0, "end_time": 10, "title": ""}],
        }
    )
    assert meta.upload_date == date(2024, 1, 31)
    assert meta.duration_s == 61
    assert meta.is_short and meta.was_live
    assert meta.channel_handle == "@kanal"
    assert meta.chapters == [{"start": 0.0, "end": 10.0, "title": "Kapitel 1"}]

    with pytest.raises(LiveContentError):
        metadata_from_info({"id": "x", "live_status": "is_upcoming"})


def test_chapters_to_vtt() -> None:
    vtt = chapters_to_vtt([{"start": 3725.5, "end": 0, "title": "A --> B"}], duration=4000)
    assert "01:02:05.500 --> 01:06:40.000" in vtt
    assert "A → B" in vtt


def test_database_from_newer_version_is_refused(tmp_path: Path) -> None:
    from sqlalchemy import text

    from app.db import make_engine
    from app.migrate import DatabaseTooNewError, run_migrations

    engine = make_engine(f"sqlite:///{tmp_path / 'tubevault.db'}")
    run_migrations(engine)
    run_migrations(engine)  # idempotent
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '0099_future'"))
    with pytest.raises(DatabaseTooNewError, match="neueren TubeVault-Version"):
        run_migrations(engine)
    engine.dispose()
