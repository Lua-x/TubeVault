from __future__ import annotations

from datetime import date
from pathlib import Path

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


def test_build_format() -> None:
    selector, sort = build_format(DownloadOptions(max_height=720, prefer_h264=True))
    assert selector == "bv*[height<=?720]+ba/b[height<=?720]/bv*+ba/b"
    assert sort == ["vcodec:h264", "acodec:aac"]
    selector, sort = build_format(DownloadOptions(max_height=None, prefer_h264=False))
    assert selector == "bv*+ba/b"
    assert sort == []


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
