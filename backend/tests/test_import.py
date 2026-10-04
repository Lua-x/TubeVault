from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.importer import id_from_name, title_from_name
from app.services.own_videos import folder_channel, parse_tags
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
    own = by_key["import:Urlaub 2019.mp4"]
    assert own["status"] == "ready" and own["kind"] == "own" and own["source"] == "Eigenes Video"
    assert own["youtube_id"].startswith("local-")
    assert by_key["import:Mein Video [namedvid001].mp4"]["kind"] == "youtube"
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


def _own_video(path: Path, **tags: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = [arg for key, value in tags.items() for arg in ("-metadata", f"{key}={value}")]
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            *metadata, str(path),
        ],
        check=True,
    )  # fmt: skip


@needs_ffmpeg
def test_own_videos(admin: TestClient, tmp_path: Path, downloader: FakeDownloader) -> None:
    """Camera and phone videos: no YouTube ID, the folder is the channel."""
    ctx = _ctx(admin)
    import_dir = tmp_path / "import"
    ctx.importer.import_dir = import_dir
    media = Path(ctx.settings.media_dir)
    beach = import_dir / "Urlaub 2024" / "Strand am Morgen.mp4"
    _own_video(beach, title="Sonnenaufgang", creation_time="2024-07-14T06:30:00Z")
    clip = import_dir / "IMG_0042.mp4"
    _own_video(clip)

    _run(admin, "scan")
    found = {c["key"]: c for c in admin.get("/api/import").json()["candidates"]}
    assert {c["kind"] for c in found.values()} == {"own"}
    assert all(c["status"] == "ready" for c in found.values())

    task = _run(admin, "run", keys=list(found), mode="copy", fetch_metadata=True)
    assert task["message"] == "2 importiert"
    assert downloader.downloads == 0

    videos = {v["title"]: v for v in admin.get("/api/videos").json()["items"]}
    assert set(videos) == {"Sonnenaufgang", "IMG 0042"}
    sunrise = admin.get(f"/api/videos/{videos['Sonnenaufgang']['id']}").json()
    assert sunrise["is_local"] is True and sunrise["source_url"] is None
    assert sunrise["upload_date"] == "2024-07-14" and sunrise["has_thumbnail"] is True
    assert sunrise["channel"]["name"] == "Urlaub 2024" and sunrise["channel"]["is_local"] is True
    assert videos["IMG 0042"]["channel"]["name"] == "Eigene Videos"
    assert admin.get(f"/api/videos/{sunrise['id']}/stream").status_code == 200
    target = media / "Urlaub 2024" / "2024" / f"Sonnenaufgang [{sunrise['youtube_id']}].mp4"
    assert target.is_file()
    assert 'type="tubevault"' in target.with_suffix(".nfo").read_text(encoding="utf-8")

    # Copies are recognised by their content, YouTube features stay away.
    _run(admin, "scan")
    rescanned = {c["key"]: c for c in admin.get("/api/import").json()["candidates"]}
    assert all(c["status"] == "known" for c in rescanned.values())
    assert admin.post(f"/api/videos/{sunrise['id']}/comments").status_code == 409
    assert admin.post(f"/api/videos/{sunrise['id']}/redownload").status_code == 409
    assert admin.get(f"/api/videos/{sunrise['id']}/segments").json()["segments"] == []

    # A kids profile gets the holiday folder like any channel.
    channel_id = sunrise["channel"]["id"]
    created = admin.post(
        "/api/users",
        json={
            "username": "kind",
            "password": "passwort1",
            "channel_access": "selected",
            "channel_ids": [channel_id],
        },
    )
    assert created.status_code == 201, created.text


@needs_ffmpeg
def test_own_videos_in_media_server_mode(admin: TestClient, tmp_path: Path) -> None:
    ctx = _ctx(admin)
    ctx.importer.import_dir = tmp_path / "import"
    _own_video(ctx.importer.import_dir / "Familie" / "Geburtstag.mp4")
    current = admin.get("/api/settings").json()
    admin.put("/api/settings", json={**current, "youtube_enabled": False})
    _run(admin, "scan")
    keys = [c["key"] for c in admin.get("/api/import").json()["candidates"]]
    assert _run(admin, "run", keys=keys, mode="move")["message"] == "1 importiert"
    assert admin.get("/api/videos").json()["items"][0]["title"] == "Geburtstag"


def test_embedded_tags() -> None:
    info = parse_tags({"TITLE": " Hochzeit ", "creation_time": "2023-06-01T14:00:00.000000Z"})
    assert info.title == "Hochzeit" and info.recorded == date(2023, 6, 1)
    assert parse_tags({"date": "2021-12-24"}).recorded == date(2021, 12, 24)
    assert parse_tags({"date": "irgendwann"}).recorded is None
    assert parse_tags({"comment": "Am Meer"}).description == "Am Meer"
    assert folder_channel("Urlaub/Tag 1/a.mp4")[1] == "Urlaub"
    assert folder_channel("a.mp4") == folder_channel("b.mkv")
    assert folder_channel("a.mp4")[0].startswith("local-")
