from __future__ import annotations

import threading
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from tests.conftest import FakeDownloader, add_and_wait, wait_for


def test_add_video_downloads_into_library(
    admin: TestClient, settings: Settings, downloader: FakeDownloader
) -> None:
    job = add_and_wait(admin)
    assert job["status"] == "completed"
    assert job["progress"] == 1.0
    assert job["video"]["title"] == "Video dQw4w9WgXcQ: Test"

    expected = (
        settings.media_dir / "Test Channel" / "2024" / "Video dQw4w9WgXcQ - Test [dQw4w9WgXcQ].mp4"
    )
    assert expected.is_file()

    videos = admin.get("/api/videos").json()
    assert videos["total"] == 1
    detail = admin.get(f"/api/videos/{videos['items'][0]['id']}").json()
    assert detail["status"] == "ready"
    assert detail["container"] == "mp4"
    assert detail["channel"]["name"] == "Test Channel"
    assert detail["subtitles"] == [
        {"id": detail["subtitles"][0]["id"], "lang": "de", "label": "Deutsch", "is_auto": False}
    ]
    assert [c["title"] for c in detail["chapters"]] == ["Intro", "Hauptteil"]
    assert detail["has_thumbnail"] is True


def test_mkv_per_request(admin: TestClient, settings: Settings) -> None:
    response = admin.post(
        "/api/videos", json={"url": "https://youtu.be/aaaaaaaaaaa", "container": "mkv"}
    )
    assert response.status_code == 202
    wait_for(lambda: list((settings.media_dir / "Test Channel").rglob("*.mkv")))


def test_duplicates_are_rejected(admin: TestClient) -> None:
    add_and_wait(admin)
    again = admin.post("/api/videos", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert again.status_code == 409


def test_invalid_urls(admin: TestClient) -> None:
    assert admin.post("/api/videos", json={"url": "https://vimeo.com/123"}).status_code == 400
    playlist = admin.post(
        "/api/videos", json={"url": "https://www.youtube.com/playlist?list=PL123"}
    )
    assert playlist.status_code == 400
    assert "Abos" in playlist.json()["detail"]


def test_network_error_is_retried(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.errors.append(ConnectionError("Connection reset by peer"))
    response = admin.post("/api/videos", json={"url": "https://youtu.be/bbbbbbbbbbb"})
    job_id = response.json()["id"]

    def queued_again() -> dict[str, object] | None:
        job = next(j for j in admin.get("/api/downloads").json()["items"] if j["id"] == job_id)
        return job if job["status"] == "queued" and job["next_attempt_at"] else None

    job = wait_for(queued_again)
    assert job["error_kind"] == "network"
    assert job["attempts"] == 1

    # Retry immediately instead of waiting for the backoff.
    retried = admin.post(f"/api/downloads/{job_id}/retry")
    assert retried.status_code == 200
    wait_for(
        lambda: (
            next(j for j in admin.get("/api/downloads").json()["items"] if j["id"] == job_id)[
                "status"
            ]
            == "completed"
        )
    )


def test_unavailable_video_fails_without_retry(
    admin: TestClient, downloader: FakeDownloader
) -> None:
    downloader.errors.append(Exception("ERROR: [youtube] ccccccccccc: Private video"))
    job = add_and_wait(admin, "ccccccccccc")
    assert job["status"] == "failed"
    assert job["error_kind"] == "unavailable"
    assert job["error_message"].startswith("[youtube]")
    assert job["attempts"] == 1


def test_cancel_running_download(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.gate = threading.Event()
    response = admin.post("/api/videos", json={"url": "https://youtu.be/ddddddddddd"})
    job_id = response.json()["id"]
    assert downloader.started.wait(5)

    assert admin.post(f"/api/downloads/{job_id}/cancel").status_code == 200
    wait_for(
        lambda: (
            next(j for j in admin.get("/api/downloads").json()["items"] if j["id"] == job_id)[
                "status"
            ]
            == "cancelled"
        )
    )
    assert admin.get("/api/videos").json()["total"] == 0
    assert admin.delete(f"/api/downloads/{job_id}").status_code == 204


def test_delete_video_removes_files(admin: TestClient, settings: Settings) -> None:
    add_and_wait(admin)
    video_id = admin.get("/api/videos").json()["items"][0]["id"]
    assert admin.delete(f"/api/videos/{video_id}").status_code == 204
    assert admin.get(f"/api/videos/{video_id}").status_code == 404
    assert not (settings.media_dir / "Test Channel").exists()
    assert Path(settings.media_dir).is_dir()


def test_search_and_sort(admin: TestClient) -> None:
    add_and_wait(admin, "eeeeeeeeeee")
    add_and_wait(admin, "fffffffffff")
    assert admin.get("/api/videos", params={"q": "eeeee"}).json()["total"] == 1
    assert admin.get("/api/videos", params={"q": "test channel"}).json()["total"] == 2
    titles = [
        v["title"] for v in admin.get("/api/videos", params={"sort": "title"}).json()["items"]
    ]
    assert titles == sorted(titles)


def test_settings_roundtrip(admin: TestClient) -> None:
    current = admin.get("/api/settings").json()
    assert current["downloads"]["container"] == "mp4"
    current["downloads"]["container"] = "mkv"
    current["max_concurrent_downloads"] = 3
    saved = admin.put("/api/settings", json=current)
    assert saved.status_code == 200
    assert admin.get("/api/settings").json()["downloads"]["container"] == "mkv"
    current["max_concurrent_downloads"] = 99
    assert admin.put("/api/settings", json=current).status_code == 422
