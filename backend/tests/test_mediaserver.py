from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.services.library import video_base_path
from tests.conftest import add_and_wait, wait_for


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _media(client: TestClient) -> Path:
    return Path(_ctx(client).settings.media_dir)


def _video(client: TestClient, youtube_id: str) -> dict[str, Any]:
    items = client.get("/api/videos", params={"limit": 200}).json()["items"]
    vid = next(v["id"] for v in items if v["youtube_id"] == youtube_id)
    return dict(client.get(f"/api/videos/{vid}").json())


def _file(client: TestClient, youtube_id: str) -> Path:
    ctx = _ctx(client)
    from app.models import Video

    with ctx.sessions() as db:
        video = db.query(Video).filter_by(youtube_id=youtube_id).one()
        return Path(ctx.settings.media_dir) / video.file_path


def _set_library(client: TestClient, **library: Any) -> None:
    settings = client.get("/api/settings").json()
    settings["library"].update(library)
    response = client.put("/api/settings", json=settings)
    assert response.status_code == 200, response.text
    _ctx(client).library_tasks.wait()
    task = client.get("/api/library/task").json()
    assert task is None or task["state"] == "done", task


def test_series_paths() -> None:
    path = video_base_path("Kanal", date(2026, 8, 23), "Ein Titel", "abcdefghijk", "series")
    assert path.as_posix() == "Kanal/Season 2026/2026-08-23 - Ein Titel [abcdefghijk]"
    unknown = video_base_path("Kanal", None, "T", "abcdefghijk", "series")
    assert unknown.as_posix() == "Kanal/Season 0/0000-00-00 - T [abcdefghijk]"


def test_movie_nfo_written_after_download(admin: TestClient) -> None:
    add_and_wait(admin, "nfomovie001")
    nfo = _file(admin, "nfomovie001").with_suffix(".nfo")
    root = ET.parse(nfo).getroot()
    assert root.tag == "movie"
    assert root.findtext("title") == "Video nfomovie001: Test"
    assert root.findtext("premiered") == "2024-05-01"
    assert root.find("uniqueid[@type='youtube']").text == "nfomovie001"  # type: ignore[union-attr]
    assert "Erstellt von TubeVault" in nfo.read_text()


def test_switch_to_series_and_back(admin: TestClient) -> None:
    for yid in ("seriesvid01", "seriesvid02"):
        add_and_wait(admin, yid)
    media = _media(admin)
    old_file = _file(admin, "seriesvid01")
    assert old_file.parent.name == "2024"

    _set_library(admin, layout="series")
    new_file = _file(admin, "seriesvid01")
    assert new_file.parent.relative_to(media).as_posix() == "Test Channel/Season 2024"
    assert new_file.name == "2024-05-01 - Video seriesvid01 - Test [seriesvid01].mp4"
    assert new_file.is_file() and not old_file.exists()
    assert not old_file.parent.exists()  # empty year folder is gone
    stem = new_file.stem
    assert (new_file.parent / f"{stem}-thumb.jpg").is_file()
    assert (new_file.parent / f"{stem}.de.vtt").is_file()

    # Same day: episodes 050101 and 050102 in the order of the video IDs.
    episodes = []
    for yid in ("seriesvid01", "seriesvid02"):
        root = ET.parse(_file(admin, yid).with_suffix(".nfo")).getroot()
        assert root.tag == "episodedetails"
        assert root.findtext("season") == "2024"
        episodes.append(root.findtext("episode"))
    assert episodes == ["50101", "50102"]
    show = media / "Test Channel" / "tvshow.nfo"
    assert ET.parse(show).getroot().findtext("title") == "Test Channel"

    # Streaming and thumbnails still work with the new paths.
    detail = _video(admin, "seriesvid01")
    assert admin.get(f"/api/videos/{detail['id']}/stream").status_code == 200
    assert admin.get(f"/api/videos/{detail['id']}/thumbnail").status_code == 200
    sub_id = detail["subtitles"][0]["id"]
    assert admin.get(f"/api/videos/{detail['id']}/subtitles/{sub_id}.vtt").status_code == 200

    # New downloads follow the layout.
    add_and_wait(admin, "seriesvid03")
    assert _file(admin, "seriesvid03").parent.name == "Season 2024"

    _set_library(admin, layout="tubevault")
    back = _file(admin, "seriesvid01")
    assert back.parent.relative_to(media).as_posix() == "Test Channel/2024"
    assert ET.parse(back.with_suffix(".nfo")).getroot().tag == "movie"
    assert not show.exists()
    assert not (media / "Test Channel" / "Season 2024").exists()


def test_switching_nfo_off_keeps_foreign_files(admin: TestClient) -> None:
    add_and_wait(admin, "nfoforeign1")
    add_and_wait(admin, "nfoowned001")
    foreign = _file(admin, "nfoforeign1").with_suffix(".nfo")
    foreign.write_text("<movie><title>Von Hand gepflegt</title></movie>", encoding="utf-8")
    owned = _file(admin, "nfoowned001").with_suffix(".nfo")

    _set_library(admin, write_nfo=False)
    assert foreign.is_file() and not owned.exists()
    _set_library(admin, write_nfo=True)
    assert "Von Hand gepflegt" in foreign.read_text()  # never overwritten
    assert owned.is_file()


def test_settings_wait_for_running_task(admin: TestClient) -> None:
    gate = threading.Event()
    tasks = _ctx(admin).library_tasks
    tasks.run("test", "Testaufgabe", lambda progress: gate.wait(5) and None)
    settings = admin.get("/api/settings").json()
    settings["library"]["layout"] = "series"
    response = admin.put("/api/settings", json=settings)
    assert response.status_code == 409
    assert admin.get("/api/library/task").json()["label"] == "Testaufgabe"
    gate.set()
    wait_for(lambda: not tasks.busy())
