from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import admin as admin_router
from app.services.ytdlp_updater import UpdateResult
from tests.conftest import HEADERS, add_and_wait


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _task(client: TestClient, action: str) -> dict[str, Any]:
    response = client.post(f"/api/admin/maintenance/{action}")
    assert response.status_code == 200, response.text
    _ctx(client).library_tasks.wait()
    task = client.get("/api/library/task").json()
    assert task["state"] == "done", task
    return dict(task)


def test_overview(admin: TestClient) -> None:
    add_and_wait(admin, "adminstats1")
    add_and_wait(admin, "adminstats2")
    data = admin.get("/api/admin/overview").json()
    assert data["videos"] == 2 and data["channels"] == 1
    assert data["library_size"] > 0 and data["downloads_7d"] == 2
    assert data["storage_by_channel"][0]["name"] == "Test Channel"
    assert data["storage_by_channel"][0]["videos"] == 2
    assert len(data["downloads_per_day"]) == 30
    assert data["downloads_per_day"][-1]["completed"] == 2
    assert data["versions"]["tubevault"] and data["versions"]["python"]


def test_admin_only(admin: TestClient) -> None:
    admin.post("/api/users", json={"username": "gast", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "gast", "password": "passwort1"})
    assert other.get("/api/admin/overview").status_code == 403
    assert other.post("/api/admin/restart").status_code == 403


def test_logs_group_tracebacks(admin: TestClient) -> None:
    logs_dir = Path(_ctx(admin).settings.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "tubevault.log").write_text(
        "2026-10-02 10:00:00,001 INFO    app.main: Gestartet\n"
        "2026-10-02 10:00:01,002 ERROR   app.workers: Kaputt\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1\n'
        "2026-10-02 10:00:02,003 WARNING app.subs: Vorsicht\n",
        encoding="utf-8",
    )
    entries = admin.get("/api/admin/logs", params={"level": "WARNING"}).json()
    assert [e["level"] for e in entries] == ["ERROR", "WARNING"]
    assert entries[0]["message"].startswith("Kaputt\nTraceback")
    assert len(admin.get("/api/admin/logs").json()) == 3


def test_ytdlp_update_and_restart(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    info = admin.get("/api/admin/ytdlp").json()
    assert info["loaded"] and info["latest"] is None and info["restart_required"] is False

    monkeypatch.setattr(
        admin_router, "update_ytdlp", lambda _dir: UpdateResult(True, "2099.1.1", "aktualisiert")
    )
    monkeypatch.setattr(admin_router, "_installed_ytdlp", lambda _ctx: "2099.1.1")
    update = admin.post("/api/admin/ytdlp/update").json()
    assert update["updated"] is True and update["info"]["restart_required"] is True

    restarts: list[bool] = []
    monkeypatch.setattr(admin_router, "request_restart", lambda: restarts.append(True))
    assert admin.post("/api/admin/restart").status_code == 202
    assert restarts == [True]


def test_maintenance(admin: TestClient) -> None:
    add_and_wait(admin, "maintain001")
    ctx = _ctx(admin)
    from app.models import Video

    with ctx.sessions() as db:
        video = db.query(Video).filter_by(youtube_id="maintain001").one()
        path = Path(ctx.settings.media_dir) / video.file_path
    path.rename(path.with_suffix(".bak"))
    assert "1 Dateien fehlen" in _task(admin, "verify")["message"]
    assert admin.get(f"/api/videos/{video.id}").json()["status"] == "missing"
    path.with_suffix(".bak").rename(path)
    assert "1 wieder da" in _task(admin, "verify")["message"]

    assert _task(admin, "search-index")["message"] == "Neu aufgebaut"
    assert admin.get("/api/videos", params={"q": "maintain001"}).json()["total"] == 1
    assert "MB freigegeben" in _task(admin, "cache")["message"]
    assert "1 Kanäle aktualisiert" in _task(admin, "artwork")["message"]
    assert _task(admin, "nfo")["kind"] == "nfo"
    assert admin.post("/api/admin/maintenance/unknown").status_code == 422
