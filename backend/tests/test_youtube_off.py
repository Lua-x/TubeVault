"""Media-server mode: the YouTube downloader is off – the library stays, YouTube is left alone."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.__main__ import youtube_enabled_on_disk
from app.config import Settings
from app.models import DownloadJob, JobStatus, Subscription
from tests.conftest import FakeCatalog, FakeDownloader, add_and_wait, wait_for


def _youtube(admin: TestClient, enabled: bool) -> None:
    current = admin.get("/api/settings").json()
    response = admin.put("/api/settings", json={**current, "youtube_enabled": enabled})
    assert response.status_code == 200, response.text


def test_switched_off_nothing_reaches_youtube(admin: TestClient) -> None:
    add_and_wait(admin, "keepme00001")
    video = admin.get("/api/videos").json()["items"][0]["id"]
    assert admin.get("/api/auth/status").json()["youtube"] is True

    _youtube(admin, False)
    assert admin.get("/api/auth/status").json()["youtube"] is False

    refused = [
        admin.post("/api/videos", json={"url": "https://youtu.be/newvideo001"}),
        admin.post(f"/api/videos/{video}/redownload"),
        admin.post(f"/api/videos/{video}/comments"),
        admin.get("/api/subscriptions"),
        admin.post("/api/subscriptions", json={"url": "@test"}),
        admin.get("/api/downloads"),
        admin.post("/api/admin/ytdlp/update"),
        admin.post("/api/admin/maintenance/artwork"),
    ]
    for response in refused:
        assert response.status_code == 409, response.request.url
        assert "Media-Server" in response.json()["detail"]

    # The library keeps working.
    assert admin.get(f"/api/videos/{video}/stream").status_code == 200
    assert admin.get(f"/api/videos/{video}").status_code == 200
    segments = admin.get(f"/api/videos/{video}/segments")
    assert segments.status_code == 200

    _youtube(admin, True)
    assert admin.get("/api/downloads").status_code == 200


def test_queued_downloads_wait(admin: TestClient, downloader: FakeDownloader) -> None:
    _youtube(admin, False)
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    with ctx.sessions() as db:
        job = DownloadJob(
            url="https://www.youtube.com/watch?v=waiting0001", youtube_id="waiting0001"
        )
        db.add(job)
        db.commit()
        job_id = job.id
    ctx.downloads.wake()
    time.sleep(0.3)
    assert downloader.downloads == 0
    with ctx.sessions() as db:
        assert db.get(DownloadJob, job_id).status is JobStatus.QUEUED

    _youtube(admin, True)
    ctx.downloads.wake()

    def done() -> bool:
        with ctx.sessions() as db:
            return db.get(DownloadJob, job_id).status is JobStatus.COMPLETED

    wait_for(done)


def test_subscriptions_are_not_checked(admin: TestClient, catalog: FakeCatalog) -> None:
    response = admin.post("/api/subscriptions", json={"url": "@test"})
    assert response.status_code == 201
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    wait_for(lambda: catalog.calls)
    _youtube(admin, False)
    calls = len(catalog.calls)
    with ctx.sessions() as db:
        db.execute(
            update(Subscription).values(next_check_at=datetime.now(UTC) - timedelta(hours=1))
        )
        db.commit()
    ctx.scheduler.wake()
    time.sleep(0.3)
    assert len(catalog.calls) == calls
    assert ctx.scheduler.cleanup() == []

    _youtube(admin, True)
    ctx.scheduler.wake()
    wait_for(lambda: len(catalog.calls) > calls)
    with ctx.sessions() as db:
        assert db.scalar(select(Subscription.next_check_at)) is not None


def test_startup_update_reads_the_setting(admin: TestClient, settings: Settings) -> None:
    assert youtube_enabled_on_disk(settings) is True
    _youtube(admin, False)
    assert youtube_enabled_on_disk(settings) is False
    _youtube(admin, True)
    assert youtube_enabled_on_disk(settings) is True
