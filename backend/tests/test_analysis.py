"""Media analysis: seek previews and loudness, once per file, in the background."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import analysis
from tests.conftest import add_and_wait

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

EBUR128_SUMMARY = """
[Parsed_ebur128_0 @ 0x55] Summary:

  Integrated loudness:
    I:         -16.4 LUFS
    Threshold: -26.6 LUFS

  Loudness range:
    LRA:         5.2 LU
"""


def test_plans_and_parsing() -> None:
    assert analysis.interval_for(90) == 2
    assert analysis.interval_for(400) == 5
    assert analysis.interval_for(3600) == 10
    assert analysis.thumb_size(1920, 1080) == (160, 90)
    assert analysis.thumb_size(1080, 1920) == (90, 160)  # a Short
    assert analysis.thumb_size(None, None) == (160, 90)
    plan = analysis.plan(3600, 1280, 720)
    assert plan.count == 360 and plan.sheets == 4
    assert analysis.parse_loudness(EBUR128_SUMMARY) == -16.4
    assert analysis.parse_loudness("    I:         -70.0 LUFS") is None  # silence
    assert analysis.parse_loudness("no audio") is None


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _video_with_sound(path: Path, seconds: int = 7) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=10:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "10", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )  # fmt: skip


def _import(admin: TestClient, tmp_path: Path) -> int:
    ctx = _ctx(admin)
    ctx.importer.import_dir = tmp_path / "import"
    _video_with_sound(ctx.importer.import_dir / "Garten" / "Rundgang.mp4")
    admin.post("/api/import/scan")
    ctx.library_tasks.wait()
    keys = [c["key"] for c in admin.get("/api/import").json()["candidates"]]
    admin.post("/api/import/run", json={"keys": keys, "mode": "move"})
    ctx.library_tasks.wait()
    return int(admin.get("/api/videos").json()["items"][0]["id"])


@needs_ffmpeg
def test_previews_and_loudness(admin: TestClient, tmp_path: Path) -> None:
    ctx = _ctx(admin)
    video_id = _import(admin, tmp_path)
    before = admin.get(f"/api/videos/{video_id}").json()
    assert before["trickplay"] is None and before["loudness_lufs"] is None
    assert admin.get("/api/admin/analysis").json()["trickplay_done"] == 0

    assert ctx.analyzer.run_once() is True
    assert ctx.analyzer.run_once() is False  # each part once per file

    detail = admin.get(f"/api/videos/{video_id}").json()
    trickplay = detail["trickplay"]
    assert trickplay["interval"] == 2 and trickplay["count"] == 4
    assert (trickplay["width"], trickplay["height"]) == (160, 90)
    assert trickplay["version"] > 0
    assert -40 < detail["loudness_lufs"] < 0
    sheet = admin.get(f"/api/videos/{video_id}/trickplay/1.jpg")
    assert sheet.status_code == 200 and sheet.content[:2] == b"\xff\xd8"
    assert admin.get(f"/api/videos/{video_id}/trickplay/2.jpg").status_code == 404
    state = admin.get("/api/admin/analysis").json()
    assert state == {"total": 1, "trickplay_done": 1, "loudness_done": 1, "current": None}

    # A new file is analysed again.
    ctx.analyzer.forget(video_id)
    assert admin.get(f"/api/videos/{video_id}").json()["trickplay"] is None
    assert admin.get(f"/api/videos/{video_id}/trickplay/1.jpg").status_code == 404
    assert ctx.analyzer.run_once() is True
    assert admin.get(f"/api/videos/{video_id}/trickplay/1.jpg").status_code == 200

    # Deleting the video takes the previews along.
    assert admin.delete(f"/api/videos/{video_id}").status_code == 204
    assert not ctx.analyzer.directory(video_id).exists()


@needs_ffmpeg
def test_switched_off_and_broken_files(admin: TestClient) -> None:
    ctx = _ctx(admin)
    add_and_wait(admin, "brokenfile1")  # the fake downloader writes bytes, not a video
    current = admin.get("/api/settings").json()
    off = {**current, "analysis": {"trickplay": False, "loudness": False}}
    assert admin.put("/api/settings", json=off).status_code == 200
    assert ctx.analyzer.run_once() is False

    admin.put("/api/settings", json=current)
    assert ctx.analyzer.run_once() is True
    # Tried once, nothing came out – and it is not tried again and again.
    assert ctx.analyzer.run_once() is False
    video = admin.get("/api/videos").json()["items"][0]
    detail = admin.get(f"/api/videos/{video['id']}").json()
    assert detail["trickplay"] is None and detail["loudness_lufs"] is None
