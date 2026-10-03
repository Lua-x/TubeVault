from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routers import admin as admin_router
from app.services import backups
from app.services.connectivity import Connectivity
from tests.conftest import HEADERS, FakeCatalog, FakeDownloader, add_and_wait, wait_for


@pytest.fixture
def restarts(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    calls: list[bool] = []
    monkeypatch.setattr(admin_router, "request_restart", lambda: calls.append(True))
    return calls


def _manual(client: TestClient) -> list[str]:
    return [b["name"] for b in client.get("/api/admin/backups").json()["backups"] if not b["auto"]]


def _titles(client: TestClient) -> list[str]:
    return sorted(v["title"] for v in client.get("/api/videos").json()["items"])


def test_backup_download_contains_the_database(admin: TestClient) -> None:
    add_and_wait(admin, "backup00001")
    created = admin.post("/api/admin/backups")
    assert created.status_code == 201, created.text
    name = created.json()["name"]
    assert name.startswith("tubevault-backup-") and created.json()["auto"] is False

    assert _manual(admin) == [name]
    assert admin.get("/api/admin/backups").json()["staged"] is None

    download = admin.get(f"/api/admin/backups/{name}")
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        manifest = json.loads(archive.read("backup.json"))
        assert set(archive.namelist()) == {"tubevault.db", "backup.json"}
    assert manifest["app"] == "TubeVault" and manifest["videos"] == 1 and manifest["schema"]

    assert admin.get("/api/admin/backups/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert admin.delete(f"/api/admin/backups/{name}").status_code == 204
    assert _manual(admin) == []


def test_daily_backups_keep_the_newest(admin: TestClient, settings: Settings) -> None:
    # TubeVault made the first one at start; another one only after a day.
    first = wait_for(lambda: backups.list_backups(settings))[0]
    assert first.auto
    assert backups.auto_backup_if_due(settings, keep=2) is None

    folder = backups.backups_dir(settings)
    for days in (3, 2, 1):  # pretend there are older automatic backups
        stamp = datetime.now(UTC) - timedelta(days=days)
        (folder / f"tubevault-backup-{stamp:%Y%m%d-%H%M%S}-auto.zip").write_bytes(b"x")
    manual = backups.create_backup(settings)
    assert backups.prune_auto_backups(settings, keep=2) == 2
    names = [b.name for b in backups.list_backups(settings)]
    assert manual.name in names and first.name in names and len(names) == 3


def test_restore_after_restart(
    admin: TestClient,
    settings: Settings,
    downloader: FakeDownloader,
    catalog: FakeCatalog,
    restarts: list[bool],
) -> None:
    add_and_wait(admin, "keepme00001")
    name = admin.post("/api/admin/backups").json()["name"]
    add_and_wait(admin, "dropme00001")
    assert len(_titles(admin)) == 2

    response = admin.post(f"/api/admin/backups/{name}/restore")
    assert response.status_code == 202, response.text
    assert response.json()["videos"] == 1 and restarts == [True]
    assert admin.get("/api/admin/backups").json()["staged"]["videos"] == 1

    # The restart: a new app on the same /config swaps in the backup before opening it.
    app = create_app(
        settings,
        downloader,
        catalog,
        configure_logging=False,
        connectivity=Connectivity(probe=lambda: True),
        feeds=lambda _url: [],
    )
    with TestClient(app, headers=HEADERS) as restarted:
        restarted.post("/api/auth/login", json={"username": "admin", "password": "geheim123"})
        assert _titles(restarted) == ["Video keepme00001: Test"]
        app.state.ctx.library_tasks.wait()
        task = restarted.get("/api/library/task").json()
        assert task["kind"] == "verify" and task["state"] == "done"
        # The state before the restore was backed up too, so it can be undone.
        assert len(_manual(restarted)) == 2
        assert restarted.get("/api/admin/backups").json()["staged"] is None


def test_restore_upload_checks_the_file(
    admin: TestClient, settings: Settings, restarts: list[bool]
) -> None:
    def upload(data: bytes) -> Any:
        return admin.post(
            "/api/admin/restore", content=data, headers={"Content-Type": "application/zip"}
        )

    bad = upload(b"no zip at all")
    assert bad.status_code == 400 and "keine ZIP" in bad.json()["detail"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")
    assert "Datenbank fehlt" in upload(buffer.getvalue()).json()["detail"]

    # A backup made by a newer TubeVault (unknown schema) is refused.
    path = backups.backup_path(settings, backups.create_backup(settings).name)
    with zipfile.ZipFile(path) as archive:
        db_bytes, manifest = archive.read("tubevault.db"), archive.read("backup.json")
    db_file = settings.config_dir / "newer.db"
    db_file.write_bytes(db_bytes)
    with closing(sqlite3.connect(db_file)) as db:
        db.execute("UPDATE alembic_version SET version_num = '9999_future'")
        db.commit()
    newer = io.BytesIO()
    with zipfile.ZipFile(newer, "w") as archive:
        archive.write(db_file, "tubevault.db")
        archive.writestr("backup.json", manifest)
    assert "neueren TubeVault-Version" in upload(newer.getvalue()).json()["detail"]
    assert restarts == [] and admin.get("/api/admin/backups").json()["staged"] is None

    ok = upload(path.read_bytes())
    assert ok.status_code == 202 and restarts == [True]
    assert not (settings.config_dir / ".restore-upload.zip").exists()


def test_backups_are_admin_only(admin: TestClient) -> None:
    admin.post("/api/users", json={"username": "gast", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "gast", "password": "passwort1"})
    assert other.get("/api/admin/backups").status_code == 403
    assert other.post("/api/admin/backups").status_code == 403
    assert other.post("/api/admin/restore", content=b"x").status_code == 403


def test_scheduler_makes_the_daily_backup(admin: TestClient, settings: Settings) -> None:
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    wait_for(lambda: backups.list_backups(settings))  # first maintenance round at start
    assert backups.list_backups(settings)[0].auto
    body = admin.get("/api/settings").json()
    body["backup"] = {"auto": False, "keep": 3}
    assert admin.put("/api/settings", json=body).status_code == 200
    for info in backups.list_backups(settings):
        (backups.backups_dir(settings) / info.name).unlink()
    ctx.scheduler.cleanup()
    assert backups.list_backups(settings) == []
