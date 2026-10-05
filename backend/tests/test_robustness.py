"""When things go wrong around TubeVault: a full disk, files that vanished."""

from __future__ import annotations

import errno
from typing import Any

from fastapi.testclient import TestClient

from app.core.errors import is_disk_full
from tests.conftest import FakeDownloader, add_and_wait, wait_for


def _job(client: TestClient, job_id: int) -> dict[str, Any]:
    return dict(next(j for j in client.get("/api/downloads").json()["items"] if j["id"] == job_id))


def test_recognises_a_full_disk() -> None:
    assert is_disk_full(OSError(errno.ENOSPC, "No space left on device"))
    assert is_disk_full(Exception("ERROR: unable to write data: [Errno 28] No space left"))
    assert not is_disk_full(OSError(errno.EACCES, "Permission denied"))
    assert not is_disk_full(Exception("HTTP Error 429: Too Many Requests"))


def test_full_disk_stops_the_queue_instead_of_failing_everything(
    admin: TestClient, downloader: FakeDownloader
) -> None:
    downloader.errors = [OSError(errno.ENOSPC, "No space left on device")]
    job_id = admin.post("/api/videos", json={"url": "https://youtu.be/diskfull001"}).json()["id"]

    def stopped() -> dict[str, Any] | None:
        job = _job(admin, job_id)
        return job if "Speicherplatz" in (job["error_message"] or "") else None

    job = wait_for(stopped)
    # Not the video's fault: it waits, without using up an attempt.
    assert job["status"] == "queued" and job["attempts"] == 0
    assert admin.get("/api/downloads/state").json()["paused"] is True

    # Space freed, queue resumed: the same download simply finishes.
    admin.post("/api/downloads/resume-all")
    wait_for(lambda: _job(admin, job_id)["status"] == "completed" or None)


def test_vanished_files_are_reported_not_crashed_on(admin: TestClient) -> None:
    add_and_wait(admin, "vanished001")
    video = admin.get("/api/videos").json()["items"][0]
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    for path in ctx.settings.media_dir.rglob("*vanished001*"):
        path.unlink()

    # Streaming and downloading answer 404 instead of failing with a server error.
    assert admin.get(f"/api/videos/{video['id']}/stream").status_code == 404
    assert admin.get(f"/api/videos/{video['id']}/download").status_code == 404
    assert admin.get(f"/api/videos/{video['id']}").status_code == 200

    # "Verify files" marks it missing; it no longer shows up as playable.
    admin.post("/api/admin/maintenance/verify")
    ctx.library_tasks.wait()
    assert admin.get("/api/videos").json()["items"] == []
