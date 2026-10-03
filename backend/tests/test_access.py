"""A kids profile sees only its channels – through every door, not just the lists."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers.ws import event_for
from tests.conftest import HEADERS, FakeDownloader, add_and_wait


def _video_id(client: TestClient, youtube_id: str) -> int:
    items = client.get("/api/videos", params={"q": youtube_id}).json()["items"]
    return int(items[0]["id"])


@pytest.fixture
def library(admin: TestClient, downloader: FakeDownloader) -> dict[str, Any]:
    downloader.meta_overrides["kids0000001"] = {"channel_id": "UCkids", "channel_name": "Kinder"}
    downloader.meta_overrides["kids0000002"] = {"channel_id": "UCkids", "channel_name": "Kinder"}
    for youtube_id in ("kids0000001", "kids0000002", "grown000001"):
        add_and_wait(admin, youtube_id)
    channels = {c["name"]: c["id"] for c in admin.get("/api/channels").json()}
    return {
        "kids_channel": channels["Kinder"],
        "other_channel": channels["Test Channel"],
        "kids_video": _video_id(admin, "kids0000001"),
        "other_video": _video_id(admin, "grown000001"),
    }


def _login(admin: TestClient, username: str, **access: Any) -> TestClient:
    created = admin.post(
        "/api/users", json={"username": username, "password": "passwort1", **access}
    )
    assert created.status_code == 201, created.text
    client = TestClient(admin.app, headers=HEADERS)
    client.post("/api/auth/login", json={"username": username, "password": "passwort1"})
    return client


def test_kids_profile_sees_only_its_channels(admin: TestClient, library: dict[str, Any]) -> None:
    kid = _login(admin, "kind", channel_access="selected", channel_ids=[library["kids_channel"]])
    me = kid.get("/api/auth/me").json()
    assert me["restricted"] is True and me["can_add"] is False

    listed = kid.get("/api/videos").json()
    assert listed["total"] == 2
    assert {v["channel"]["name"] for v in listed["items"]} == {"Kinder"}
    assert kid.get("/api/videos", params={"q": "grown000001"}).json()["total"] == 0
    assert (
        kid.get("/api/videos", params={"channel_id": library["other_channel"]}).json()["total"] == 0
    )
    assert [c["name"] for c in kid.get("/api/channels").json()] == ["Kinder"]
    assert kid.get("/api/system/info").json()["video_count"] == 2

    home = kid.get("/api/home").json()
    shown = [
        v
        for row in ("continue_watching", "from_subscriptions", "recently_added")
        for v in home[row]
    ]
    assert shown and all(v["channel"]["name"] == "Kinder" for v in shown)
    assert [c["name"] for c in home["channels"]] == ["Kinder"]

    # Its own channel works …
    own = library["kids_video"]
    assert kid.get(f"/api/videos/{own}").status_code == 200
    assert kid.get(f"/api/videos/{own}/stream").status_code == 200


def test_hidden_videos_are_closed_everywhere(admin: TestClient, library: dict[str, Any]) -> None:
    kid = _login(admin, "kind", channel_access="selected", channel_ids=[library["kids_channel"]])
    other = library["other_video"]
    subtitle = admin.get(f"/api/videos/{other}").json()["subtitles"][0]["id"]
    for path in (
        f"/api/videos/{other}",
        f"/api/videos/{other}/stream",
        f"/api/videos/{other}/download",
        f"/api/videos/{other}/thumbnail",
        f"/api/videos/{other}/chapters.vtt",
        f"/api/videos/{other}/segments",
        f"/api/videos/{other}/subtitles/{subtitle}.vtt",
        f"/api/videos/{other}/playback",
        f"/api/videos/{other}/hls/720/index.m3u8",
        f"/api/channels/{library['other_channel']}",
        f"/api/channels/{library['other_channel']}/avatar",
    ):
        assert kid.get(path).status_code == 404, path
    assert kid.put(f"/api/videos/{other}/progress", json={"position_s": 5}).status_code == 404
    assert kid.put(f"/api/videos/{other}/watched", json={"watched": True}).status_code == 404

    playlist = kid.post("/api/playlists", json={"name": "Meine"}).json()
    items = f"/api/playlists/{playlist['id']}/items"
    assert kid.post(items, json={"video_id": other}).status_code == 404
    assert kid.post(items, json={"video_id": library["kids_video"]}).status_code == 201

    # … and nothing to add, download or subscribe.
    assert kid.post("/api/videos", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 403
    assert kid.get("/api/downloads").status_code == 403
    assert kid.get("/api/subscriptions").status_code == 403


def test_view_only_account(admin: TestClient, library: dict[str, Any]) -> None:
    viewer = _login(admin, "oma", may_add=False)
    me = viewer.get("/api/auth/me").json()
    assert me["restricted"] is False and me["can_add"] is False
    assert viewer.get("/api/videos").json()["total"] == 3
    assert (
        viewer.post("/api/videos", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 403
    )
    assert viewer.post("/api/subscriptions", json={"url": "@test"}).status_code == 403
    assert viewer.post("/api/downloads/pause-all").status_code == 403


def test_admin_changes_access(admin: TestClient, library: dict[str, Any]) -> None:
    kid = _login(admin, "kind")
    kid_id = kid.get("/api/auth/me").json()["id"]
    assert kid.get("/api/videos").json()["total"] == 3

    changed = admin.patch(
        f"/api/users/{kid_id}",
        json={"channel_access": "selected", "channel_ids": [library["kids_channel"]]},
    ).json()
    assert changed["channel_ids"] == [library["kids_channel"]] and changed["restricted"] is True
    assert kid.get("/api/videos").json()["total"] == 2
    assert kid.patch(f"/api/users/{kid_id}", json={"channel_access": "all"}).status_code == 403

    admin.patch(f"/api/users/{kid_id}", json={"channel_access": "all"})
    assert kid.get("/api/videos").json()["total"] == 3

    # Admins always see everything, whatever is stored for them.
    me = admin.get("/api/auth/me").json()
    admin.patch(f"/api/users/{me['id']}", json={"channel_access": "selected", "channel_ids": []})
    assert admin.get("/api/videos").json()["total"] == 3


def test_live_events_for_restricted_accounts() -> None:
    job = {"type": "job.updated", "job": {"video": {"title": "Geheim"}}}
    video = {"type": "video.updated", "video": {"title": "Geheim"}}
    assert event_for(job, restricted=False) == job
    assert event_for(job, restricted=True) is None
    assert event_for(video, restricted=True) == {"type": "video.updated"}
    assert (
        event_for({"type": "subscription.updated", "subscription_id": 1}, restricted=True) is None
    )
