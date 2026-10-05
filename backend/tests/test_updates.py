"""Updating from every earlier release keeps everything the old version stored.

The fixtures in tests/fixtures/upgrades were made by each release's own code – its API and
its test fakes (see build_fixture.py there): a database, the values that must survive, and
from 0.5 on a backup made by that version.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.ports import LEGACY_PORT
from app.main import create_app
from app.migrate import MIGRATIONS_DIR
from app.routers import admin as admin_router
from app.services.backups import DB_NAME
from app.services.connectivity import Connectivity
from tests.conftest import HEADERS, FakeCatalog, FakeDownloader, add_and_wait

FIXTURES = Path(__file__).parent / "fixtures" / "upgrades"


def _version(name: str) -> tuple[int, ...]:
    return tuple(int(part) for part in name.lstrip("v").split("."))


RELEASES = sorted((p.name.removesuffix(".json") for p in FIXTURES.glob("v*.json")), key=_version)
WITH_BACKUP = [r for r in RELEASES if (FIXTURES / f"{r}.zip").is_file()]


def _head() -> str:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _start(settings: Settings, downloader: FakeDownloader, catalog: FakeCatalog) -> TestClient:
    app = create_app(
        settings,
        downloader,
        catalog,
        configure_logging=False,
        connectivity=Connectivity(probe=lambda: True),
        feeds=lambda _url: [],
        media_analysis=False,
        speech_recognition=False,
    )
    return TestClient(app, headers=HEADERS)


def _setting(settings: dict[str, Any], dotted: str) -> Any:
    value: Any = settings
    for part in dotted.split("."):
        value = value[part]
    return value


def _check(client: TestClient, expected: dict[str, Any]) -> None:
    """Everything the old version stored is still there and works."""
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": expected["password"]}
    )
    assert login.status_code == 200, login.text

    videos = client.get("/api/videos", params={"limit": 100}).json()["items"]
    assert sorted(v["youtube_id"] for v in videos) == expected["youtube_ids"]
    users = sorted(u["username"] for u in client.get("/api/users").json())
    assert users == expected["users"]

    settings = client.get("/api/settings").json()
    for dotted, value in expected["settings"].items():
        assert _setting(settings, dotted) == value, dotted

    if "progress" in expected:
        detail = client.get(f"/api/videos/{expected['progress']['video']}").json()
        assert detail["progress"]["position_s"] == expected["progress"]["position_s"]
    playlists = {p["name"]: p for p in client.get("/api/playlists").json()}
    if "playlist" in expected:
        mine = playlists[expected["playlist"]["name"]]
        items = client.get(f"/api/playlists/{mine['id']}").json()["videos"]
        assert len(items) == expected["playlist"]["videos"]
    if "watch_later" in expected:
        later = client.get("/api/playlists/watch-later").json()
        assert len(later["videos"]) == expected["watch_later"]
    if "subscriptions" in expected:
        titles = [s["title"] for s in client.get("/api/subscriptions").json()]
        assert titles == expected["subscriptions"]
    if "token" in expected:
        script = TestClient(client.app, headers={"Authorization": f"Bearer {expected['token']}"})
        assert script.get("/api/videos").status_code == 200
    if "family" in expected:
        me = client.get("/api/auth/me").json()
        assert me["has_pin"] is expected["family"]["has_pin"]
        devices = [d["name"] for d in client.get("/api/family/devices").json()]
        assert devices == [expected["family"]["device"]]

    # And the new version keeps working on top of the old data.
    assert add_and_wait(client, "afterupdate")["status"] == "completed"
    assert client.get("/api/admin/overview").status_code == 200


def _media_files_of(backup: Path, settings: Settings) -> None:
    """The videos are still on disk, as on the server the backup came from."""
    unpacked = settings.config_dir / "peek.db"
    with zipfile.ZipFile(backup) as archive:
        unpacked.write_bytes(archive.read(DB_NAME))
    with contextlib.closing(sqlite3.connect(unpacked)) as conn:
        paths = [row[0] for row in conn.execute("SELECT file_path FROM videos") if row[0]]
    unpacked.unlink()
    for relative in paths:
        (settings.media_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (settings.media_dir / relative).write_bytes(b"video")


@pytest.mark.parametrize("release", RELEASES)
def test_update_from_every_release(
    release: str, settings: Settings, downloader: FakeDownloader, catalog: FakeCatalog
) -> None:
    expected = json.loads((FIXTURES / f"{release}.json").read_text())
    settings.config_dir.mkdir(parents=True)
    database = settings.config_dir / "tubevault.db"
    with gzip.open(FIXTURES / f"{release}.db.gz") as packed, database.open("wb") as target:
        shutil.copyfileobj(packed, target)

    with _start(settings, downloader, catalog) as client:
        # An install from before 1.0 keeps its port (see app/core/ports.py).
        assert settings.port == LEGACY_PORT
        _check(client, expected)
    with contextlib.closing(sqlite3.connect(database)) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == _head()


@pytest.mark.parametrize("release", WITH_BACKUP)
def test_restore_a_backup_from_every_release(
    release: str,
    admin: TestClient,
    settings: Settings,
    downloader: FakeDownloader,
    catalog: FakeCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin_router, "request_restart", lambda: None)
    expected = json.loads((FIXTURES / f"{release}.json").read_text())
    response = admin.post(
        "/api/admin/restore",
        content=(FIXTURES / f"{release}.zip").read_bytes(),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 202, response.text
    _media_files_of(FIXTURES / f"{release}.zip", settings)

    # The restart swaps the old database in and migrates it.
    with _start(settings, downloader, catalog) as restarted:
        _check(restarted, expected)
