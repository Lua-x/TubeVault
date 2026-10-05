"""Builds an upgrade fixture with this version's own code.

Dropped into the checkout of an old release and run with its own test fixtures; writes the
database, the values a newer TubeVault must still show, and (from 0.5 on) a backup.
"""

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from tests.conftest import add_and_wait


def _ok(response: Any) -> bool:
    return response.status_code < 400


def _items(payload: Any) -> list[dict[str, Any]]:
    return payload["items"] if isinstance(payload, dict) else payload


def test_build_upgrade_fixture(admin: Any, settings: Any) -> None:
    out = Path(os.environ["FIXTURE_OUT"])  # e.g. …/v0.9.0 – the suffixes are added

    def path(suffix: str) -> Path:
        return out.parent / f"{out.name}{suffix}"

    expected: dict[str, Any] = {"password": "geheim123"}

    for youtube_id in ("upgrade0001", "upgrade0002", "upgrade0003"):
        job = add_and_wait(admin, youtube_id)
        assert job["status"] == "completed", job
    videos = _items(admin.get("/api/videos").json())
    ids = sorted(v["id"] for v in videos)
    expected["youtube_ids"] = sorted(v["youtube_id"] for v in videos)

    created = admin.post("/api/users", json={"username": "familie", "password": "passwort1"})
    expected["users"] = ["admin", "familie"] if _ok(created) else ["admin"]

    # Settings this version knows, changed away from their defaults.
    current = admin.get("/api/settings").json()
    changes: dict[str, Any] = {}

    def change(section: str | None, key: str, value: Any) -> None:
        if section and section not in current:
            return  # not in this version yet
        target = current[section] if section else current
        if key in target:
            target[key] = value
            changes[f"{section}.{key}" if section else key] = value

    change("downloads", "container", "mkv")
    change("downloads", "max_height", 720)
    change("downloads", "subtitle_languages", ["de", "fr"])
    change("downloads", "sponsorblock_mode", "skip")
    change("downloads", "comments", True)
    change(None, "max_concurrent_downloads", 3)
    change("transcoding", "max_height", 720)
    change("library", "write_nfo", False)
    change("backup", "keep", 9)
    change("automation", "rss", False)
    change("analysis", "loudness", False)
    saved = admin.put("/api/settings", json=current)
    assert _ok(saved), saved.text
    expected["settings"] = changes

    progress = admin.put(f"/api/videos/{ids[0]}/progress", json={"position_s": 42})
    if _ok(progress):
        expected["progress"] = {"video": ids[0], "position_s": 42}

    playlist = admin.post("/api/playlists", json={"name": "Lieblinge"})
    if _ok(playlist):
        playlist_id = playlist.json()["id"]
        for video_id in ids[1:]:
            admin.post(f"/api/playlists/{playlist_id}/items", json={"video_id": video_id})
        expected["playlist"] = {"name": "Lieblinge", "videos": len(ids) - 1}

    later = admin.get("/api/playlists/watch-later")
    if _ok(later):
        admin.post(f"/api/playlists/{later.json()['id']}/items", json={"video_id": ids[2]})
        expected["watch_later"] = 1

    subscription = admin.post("/api/subscriptions", json={"url": "@test"})
    if _ok(subscription):
        expected["subscriptions"] = [subscription.json().get("title") or "Test Channel"]

    token = admin.post("/api/auth/tokens", json={"name": "Skript", "scope": "read"})
    if _ok(token):
        expected["token"] = token.json()["token"]

    device = admin.post("/api/family/devices", json={"name": "Wohnzimmer"})
    family = admin.put("/api/auth/me/family", json={"on_family_devices": True, "pin": "2468"})
    if _ok(device) and _ok(family):
        expected["family"] = {"device": "Wohnzimmer", "has_pin": True}

    backup = admin.post("/api/admin/backups")
    if _ok(backup):
        newest = max(
            (settings.config_dir / "backups").glob("*.zip"), key=lambda p: p.stat().st_mtime
        )
        shutil.copy(newest, path(".zip"))
        expected["backup"] = True

    database = settings.config_dir / "tubevault.db"
    with sqlite3.connect(database) as source:
        expected["schema"] = source.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        target = sqlite3.connect(path(".db"))
        source.backup(target)
        target.execute("VACUUM")
        target.close()
    path(".json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
