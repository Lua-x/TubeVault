from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.importer import id_from_name, title_from_name
from tests.conftest import FakeDownloader

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_ids_from_file_names() -> None:
    assert id_from_name("Mein Video [dQw4w9WgXcQ]") == "dQw4w9WgXcQ"
    assert id_from_name("Mein Video (dQw4w9WgXcQ)") == "dQw4w9WgXcQ"
    assert id_from_name("Mein_Video-dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert id_from_name("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert id_from_name("Urlaub 2019") is None
    assert title_from_name("Mein_Video-dQw4w9WgXcQ", "dQw4w9WgXcQ") == "Mein Video"


def _video(path: Path, seconds: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=10:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )  # fmt: skip


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _run(client: TestClient, path: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/import/{path}", json=body or None)
    assert response.status_code == 200, response.text
    _ctx(client).library_tasks.wait()
    task = client.get("/api/library/task").json()
    assert task["state"] == "done", task
    return dict(task)


@needs_ffmpeg
def test_import_from_folder_and_media(
    admin: TestClient, tmp_path: Path, downloader: FakeDownloader
) -> None:
    ctx = _ctx(admin)
    import_dir = tmp_path / "import"
    ctx.importer.import_dir = import_dir
    media = Path(ctx.settings.media_dir)

    # yt-dlp archive with info.json, a subtitle as .srt and a thumbnail
    archived = import_dir / "Kanal" / "Alt-infojson001.mkv"
    _video(archived)
    archived.with_suffix(".info.json").write_text(
        json.dumps(
            {
                "id": "infojson001",
                "title": "Aus dem Archiv",
                "channel": "Archivkanal",
                "channel_id": "UCarchive",
                "upload_date": "20190304",
                "duration": 3,
            }
        ),
        encoding="utf-8",
    )
    archived.with_name("Alt-infojson001.de.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8"
    )
    # ID only in the name; YouTube metadata comes from the (fake) downloader
    named = import_dir / "Mein Video [namedvid001].mp4"
    _video(named)
    # No ID at all
    _video(import_dir / "Urlaub 2019.mp4")
    # Somewhere below /media but unknown to the library
    loose = media / "Altes Archiv" / "Lose Datei [loosefile01].mp4"
    _video(loose)

    _run(admin, "scan")
    overview = admin.get("/api/import").json()
    by_key = {c["key"]: c for c in overview["candidates"]}
    assert by_key["import:Kanal/Alt-infojson001.mkv"]["source"] == "info.json"
    assert by_key["import:Kanal/Alt-infojson001.mkv"]["title"] == "Aus dem Archiv"
    assert by_key["import:Mein Video [namedvid001].mp4"]["status"] == "ready"
    assert by_key["import:Urlaub 2019.mp4"]["status"] == "unknown"
    assert by_key["media:Altes Archiv/Lose Datei [loosefile01].mp4"]["root"] == "media"

    # Keeping files in place only works below /media.
    response = admin.post(
        "/api/import/run", json={"keys": ["import:Mein Video [namedvid001].mp4"], "mode": "keep"}
    )
    assert response.status_code == 422

    task = _run(
        admin,
        "run",
        keys=["import:Kanal/Alt-infojson001.mkv", "import:Mein Video [namedvid001].mp4"],
        mode="copy",
    )
    assert task["message"] == "2 importiert"
    assert archived.is_file() and named.is_file()  # copied, not moved

    items = {v["youtube_id"]: v for v in admin.get("/api/videos").json()["items"]}
    old = admin.get(f"/api/videos/{items['infojson001']['id']}").json()
    assert old["title"] == "Aus dem Archiv" and old["channel"]["name"] == "Archivkanal"
    assert old["upload_date"] == "2019-03-04" and old["height"] == 180
    assert old["has_thumbnail"] is True  # made by ffmpeg
    assert [s["lang"] for s in old["subtitles"]] == ["de"]
    sub = admin.get(f"/api/videos/{old['id']}/subtitles/{old['subtitles'][0]['id']}.vtt")
    assert sub.text.startswith("WEBVTT")
    assert admin.get(f"/api/videos/{old['id']}/stream").status_code == 200
    assert (media / "Archivkanal" / "2019" / "Aus dem Archiv [infojson001].mkv").is_file()
    assert items["namedvid001"]["title"] == "Video namedvid001: Test"  # from "YouTube"

    task = _run(admin, "run", keys=["media:Altes Archiv/Lose Datei [loosefile01].mp4"], mode="keep")
    assert task["message"] == "1 importiert"
    assert loose.is_file()
    rescanned = {c["key"]: c for c in admin.get("/api/import").json()["candidates"]}
    assert "media:Altes Archiv/Lose Datei [loosefile01].mp4" not in rescanned  # in the library
    assert rescanned["import:Mein Video [namedvid001].mp4"]["status"] == "known"


@needs_ffmpeg
def test_import_without_youtube(
    admin: TestClient, tmp_path: Path, downloader: FakeDownloader
) -> None:
    ctx = _ctx(admin)
    ctx.importer.import_dir = tmp_path / "import"
    source = ctx.importer.import_dir / "Vortrag_offline-offlinevid1.mp4"
    _video(source)
    _run(admin, "scan")
    task = _run(
        admin,
        "run",
        keys=["import:Vortrag_offline-offlinevid1.mp4"],
        mode="move",
        fetch_metadata=False,
    )
    assert task["message"] == "1 importiert"
    assert not source.exists()  # moved
    video = admin.get("/api/videos").json()["items"][0]
    assert video["title"] == "Vortrag offline"
    assert video["channel"]["name"] == "Unbekannter Kanal"
    assert downloader.downloads == 0
