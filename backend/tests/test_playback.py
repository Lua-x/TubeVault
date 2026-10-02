from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Video
from app.services.transcode import (
    HlsJob,
    MediaInfo,
    available_heights,
    can_copy_into_mp4,
    codec_string,
    hls_command,
    hls_playlist,
    parse_probe,
    remux_command,
    segment_count,
    target_height,
)
from tests.conftest import add_and_wait, wait_for

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")

# --- pure functions ------------------------------------------------------------------


def test_parse_probe_skips_cover_art() -> None:
    info = parse_probe(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
                {"codec_type": "video", "codec_name": "vp9", "width": 1920, "height": 1080},
                {"codec_type": "audio", "codec_name": "opus", "channels": 2},
            ],
            "format": {"duration": "61.5", "format_name": "matroska,webm"},
        }
    )
    assert (info.video_codec, info.height, info.audio_codec, info.duration) == (
        "vp9",
        1080,
        "opus",
        61.5,
    )
    assert codec_string(info.video_codec) == "vp09.00.40.08"
    assert can_copy_into_mp4(info)
    assert not can_copy_into_mp4(MediaInfo(10, "mpeg2video", 720, 576, "mp2", 2, "mpeg"))


def test_qualities() -> None:
    assert available_heights(1080, 1080) == [720, 480, 360]
    assert available_heights(2160, 1080) == [1080, 720, 480, 360]
    assert available_heights(480, 1080) == [360]
    assert target_height("source", 2160, 1080) == 1080
    assert target_height("720", 480, 1080) == 480  # never upscale
    with pytest.raises(ValueError):
        target_height("999", 1080, 1080)


def test_hls_playlist_has_fixed_segments() -> None:
    playlist = hls_playlist(20.0)
    assert segment_count(20.0) == 4 and segment_count(18.0) == 3
    assert playlist.count("#EXTINF:6.000000,") == 3
    assert "#EXTINF:2.000000,\n3.ts" in playlist
    assert playlist.rstrip().endswith("#EXT-X-ENDLIST")


def _job(mode: Any, height: int = 720, source_height: int | None = 1080) -> HlsJob:
    return HlsJob(
        source=Path("/media/a.mkv"),
        directory=Path("/cache/x"),
        start_segment=5,
        height=height,
        source_height=source_height,
        mode=mode,
    )


def test_hls_commands_per_mode() -> None:
    software = hls_command(_job("software"), ffmpeg="ffmpeg")
    joined = " ".join(software)
    assert "-ss 30 -i /media/a.mkv" in joined
    assert "-output_ts_offset 30" in joined and "-start_number 5" in joined
    assert "scale=-2:720,format=yuv420p" in joined and "libx264" in joined
    assert "expr:gte(t,n_forced*6)" in joined

    vaapi = " ".join(hls_command(_job("vaapi"), ffmpeg="ffmpeg"))
    assert "-hwaccel vaapi" in vaapi and "scale_vaapi=w=-2:h=720:format=nv12" in vaapi
    assert "h264_vaapi" in vaapi
    fallback = " ".join(hls_command(_job("vaapi-swdec"), ffmpeg="ffmpeg"))
    assert "-hwaccel" not in fallback and "hwupload" in fallback

    nvenc = " ".join(hls_command(_job("nvenc", height=1080), ffmpeg="ffmpeg"))
    assert "-hwaccel cuda" in nvenc and "scale_cuda=format=yuv420p" in nvenc  # no downscale
    assert "h264_nvenc" in nvenc

    assert "hvc1" in remux_command(Path("a.mkv"), Path("b.mp4"), "hevc", ffmpeg="ffmpeg")
    assert "hvc1" not in remux_command(Path("a.mkv"), Path("b.mp4"), "h264", ffmpeg="ffmpeg")


def test_transcode_settings_validation(admin: TestClient) -> None:
    settings = admin.get("/api/settings").json()
    assert settings["transcoding"]["hwaccel"] == "none"
    settings["transcoding"]["vaapi_device"] = "/etc/passwd"
    assert admin.put("/api/settings", json=settings).status_code == 422
    settings["transcoding"].update(hwaccel="vaapi", vaapi_device="/dev/dri/renderD129")
    saved = admin.put("/api/settings", json=settings).json()
    assert saved["transcoding"]["vaapi_device"] == "/dev/dri/renderD129"


# --- with ffmpeg ---------------------------------------------------------------------


def _make_video(path: Path, seconds: int = 20, size: str = "854x480") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )  # fmt: skip


def _ffprobe(path: Path) -> dict[str, Any]:
    out = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return dict(json.loads(out)["format"])


def _library_video(admin: TestClient, youtube_id: str, suffix: str = ".mp4") -> int:
    """A library entry whose file is a real (tiny) video."""
    add_and_wait(admin, youtube_id)
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    with ctx.sessions() as db:
        video = db.query(Video).filter_by(youtube_id=youtube_id).one()
        old = ctx.settings.media_dir / video.file_path
        new = old.with_suffix(suffix)
        old.unlink()
        _make_video(new)
        video.file_path = str(new.relative_to(ctx.settings.media_dir))
        db.commit()
        return int(video.id)


@needs_ffmpeg
def test_hls_segments_line_up_after_seeking(admin: TestClient) -> None:
    vid = _library_video(admin, "hlsvideo001")
    info = admin.get(f"/api/videos/{vid}/playback").json()
    assert info["height"] == 480 and info["qualities"] == [360]
    assert info["video_codec"] and info["can_remux"] is True

    playlist = admin.get(f"/api/videos/{vid}/hls/360/index.m3u8")
    assert playlist.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert playlist.text.count(".ts") == 4

    # Jump straight to segment 2 (a fresh ffmpeg run starting at 12 s), then segment 0.
    second = admin.get(f"/api/videos/{vid}/hls/360/2.ts")
    assert second.status_code == 200 and second.headers["content-type"] == "video/mp2t"
    first = admin.get(f"/api/videos/{vid}/hls/360/0.ts")
    assert first.status_code == 200

    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    folder = next((ctx.settings.cache_dir / "hls").glob(f"{vid}-360-*"))
    seg0, seg2 = _ffprobe(folder / "seg_00000.ts"), _ffprobe(folder / "seg_00002.ts")
    # Both runs share one timeline: segment 2 starts 12 s after segment 0.
    assert float(seg2["start_time"]) - float(seg0["start_time"]) == pytest.approx(12, abs=0.1)
    assert float(seg0["duration"]) == pytest.approx(6, abs=0.2)

    assert admin.get(f"/api/videos/{vid}/hls/360/4.ts").status_code == 404
    assert admin.get(f"/api/videos/{vid}/hls/123/0.ts").status_code == 404

    admin.delete(f"/api/videos/{vid}")
    assert not folder.exists()  # cache is purged with the video


@needs_ffmpeg
def test_remux_mkv_to_mp4(admin: TestClient) -> None:
    vid = _library_video(admin, "remuxvideo1", suffix=".mkv")
    assert admin.get(f"/api/videos/{vid}/playback").json()["container"] == "mkv"
    assert admin.get(f"/api/videos/{vid}/remux").json()["state"] == "none"
    assert admin.get(f"/api/videos/{vid}/remux.mp4").status_code == 404

    assert admin.post(f"/api/videos/{vid}/remux").json()["state"] in ("running", "ready")
    wait_for(lambda: admin.get(f"/api/videos/{vid}/remux").json()["state"] == "ready", 30)

    response = admin.get(f"/api/videos/{vid}/remux.mp4", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206 and len(response.content) == 100
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    remuxed = next((ctx.settings.cache_dir / "remux").glob(f"{vid}-*.mp4"))
    assert "mp4" in _ffprobe(remuxed)["format_name"]


@needs_ffmpeg
def test_hardware_endpoints(admin: TestClient) -> None:
    hardware = admin.get("/api/transcoding/hardware").json()
    assert set(hardware) == {"render_devices", "nvidia", "encoders"}
    result = admin.post("/api/transcoding/test", json={"hwaccel": "none"}).json()
    assert result["ok"] is True
    assert admin.get("/api/transcoding/sessions").json() == []
