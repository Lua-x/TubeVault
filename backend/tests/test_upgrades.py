from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.models import Video
from app.services.upgrades import QualityUpgrades, best_height
from tests.conftest import HEADERS, FakeDownloader, add_and_wait, wait_for


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _video(client: TestClient, youtube_id: str) -> Video:
    with _ctx(client).sessions() as db:
        video = db.query(Video).filter_by(youtube_id=youtube_id).one()
        db.expunge(video)
        return video


def _job(client: TestClient, job_id: int) -> dict[str, Any]:
    return dict(next(j for j in client.get("/api/downloads").json()["items"] if j["id"] == job_id))


def _files(client: TestClient, video: Video) -> list[str]:
    folder = Path(_ctx(client).settings.media_dir) / Path(video.file_path or "").parent
    return sorted(p.name for p in folder.iterdir())


def test_best_height() -> None:
    info = {
        "formats": [
            {"height": 360, "vcodec": "avc1"},
            {"height": 2160, "vcodec": "vp9"},
            {"height": 1080, "vcodec": "avc1"},
            {"height": None, "vcodec": "none"},  # audio
        ]
    }
    assert best_height(info, None) == 2160
    assert best_height(info, 1080) == 1080
    assert best_height({}, None) is None


def test_redownload_replaces_the_file_in_place(
    admin: TestClient, downloader: FakeDownloader
) -> None:
    downloader.height = 720
    add_and_wait(admin, "upgrade0001")
    old = _video(admin, "upgrade0001")
    admin.put(f"/api/videos/{old.id}/progress", json={"position_s": 42})
    playlist = admin.post("/api/playlists", json={"name": "Liste"}).json()
    admin.post(f"/api/playlists/{playlist['id']}/items", json={"video_id": old.id})

    # The new version comes as MKV: the old MP4 must go, everything else stays.
    settings = admin.get("/api/settings").json()
    settings["downloads"]["container"] = "mkv"
    admin.put("/api/settings", json=settings)
    downloader.height = 1080
    downloader.gate = threading.Event()
    job = admin.post(f"/api/videos/{old.id}/redownload").json()
    assert job["upgrade"] is True
    assert admin.post(f"/api/videos/{old.id}/redownload").status_code == 409
    wait_for(lambda: _job(admin, job["id"])["status"] == "running")
    # While the better version downloads, the old one keeps playing.
    assert admin.get(f"/api/videos/{old.id}").json()["status"] == "ready"
    assert admin.get(f"/api/videos/{old.id}/stream").status_code == 200
    downloader.gate.set()
    wait_for(lambda: _job(admin, job["id"])["status"] == "completed")

    new = _video(admin, "upgrade0001")
    assert new.id == old.id and new.height == 1080
    assert new.file_path == str(Path(old.file_path or "").with_suffix(".mkv"))
    files = _files(admin, new)
    assert Path(new.file_path).name in files and Path(old.file_path or "").name not in files
    assert not [name for name in files if ".new" in name]
    detail = admin.get(f"/api/videos/{old.id}").json()
    assert detail["progress"]["position_s"] == 42
    assert [v["id"] for v in admin.get(f"/api/playlists/{playlist['id']}").json()["videos"]] == [
        old.id
    ]


def test_failed_upgrade_keeps_the_old_file(admin: TestClient, downloader: FakeDownloader) -> None:
    add_and_wait(admin, "upgrade0002")
    video = _video(admin, "upgrade0002")
    before = _files(admin, video)
    downloader.errors.append(Exception("ERROR: [youtube] upgrade0002: Private video"))
    job = admin.post(f"/api/videos/{video.id}/redownload").json()
    wait_for(lambda: _job(admin, job["id"])["status"] == "failed")
    assert admin.get(f"/api/videos/{video.id}").json()["status"] == "ready"
    assert _files(admin, video) == before


def test_redownload_is_admin_only(admin: TestClient) -> None:
    add_and_wait(admin, "upgrade0003")
    video = _video(admin, "upgrade0003")
    admin.post("/api/users", json={"username": "gast", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "gast", "password": "passwort1"})
    assert other.post(f"/api/videos/{video.id}/redownload").status_code == 403


def test_low_quality_is_upgraded_automatically(
    admin: TestClient, downloader: FakeDownloader
) -> None:
    downloader.height = 720
    add_and_wait(admin, "upgrade0004")
    video = _video(admin, "upgrade0004")
    ctx = _ctx(admin)
    with ctx.sessions() as db:
        db.get(Video, video.id).downloaded_at = datetime.now(UTC) - timedelta(hours=3)
        db.commit()
    upgrades = QualityUpgrades(
        ctx.sessions,
        ctx.settings.media_dir,
        downloader,
        on_queued=lambda _ids: ctx.downloads.wake(),
    )

    # YouTube still has nothing better: no download.
    sd = {"height": 720, "vcodec": "avc1"}
    downloader.meta_overrides["upgrade0004"] = {"raw": {"formats": [sd]}}
    assert upgrades.run_round() == []

    upgrades._checked.clear()  # pretend half a day passed
    hd = {"height": 1080, "vcodec": "avc1"}
    downloader.meta_overrides["upgrade0004"] = {"raw": {"formats": [sd, hd]}}
    downloader.height = 1080
    queued = upgrades.run_round()
    assert len(queued) == 1
    wait_for(lambda: _job(admin, queued[0])["status"] == "completed")
    assert _video(admin, "upgrade0004").height == 1080
    upgrades._checked.clear()
    assert upgrades.run_round() == []  # at the target now

    body = admin.get("/api/settings").json()
    body["automation"]["upgrade_quality"] = False
    admin.put("/api/settings", json=body)
    assert upgrades.run_round() == []
