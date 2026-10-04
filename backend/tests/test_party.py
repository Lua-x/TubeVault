"""Watching together: one room per video, everyone follows play, pause and seeking."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import party
from app.services.rooms import MAX_PER_OWNER, Member, RoomError, Rooms
from tests.conftest import FakeDownloader, add_and_wait
from tests.test_access import _login
from tests.test_remote import _until


@pytest.fixture
def videos(admin: TestClient, downloader: FakeDownloader) -> dict[str, int]:
    downloader.meta_overrides["partykids01"] = {"channel_id": "UCkids", "channel_name": "Kinder"}
    for youtube_id in ("partykids01", "partygrown1"):
        add_and_wait(admin, youtube_id)
    found = {v["youtube_id"]: v for v in admin.get("/api/videos").json()["items"]}
    return {
        "kids": found["partykids01"]["id"],
        "grown": found["partygrown1"]["id"],
        "kids_channel": found["partykids01"]["channel"]["id"],
    }


def test_watch_together(admin: TestClient, videos: dict[str, int]) -> None:
    friend = _login(admin, "freundin")
    room = admin.post("/api/party", json={"video_id": videos["grown"]}).json()
    assert room["video_id"] == videos["grown"]

    with admin.websocket_connect(f"/api/party/{room['id']}") as host:
        joined = _until(host, "joined")
        assert joined["paused"] is True and joined["position"] == 0
        with friend.websocket_connect(f"/api/party/{room['id']}") as guest:
            _until(guest, "joined")
            names = {m["name"]: m["role"] for m in _until(host, "presence")["members"]}
            # The host may already have seen the first presence; wait for both names.
            while len(names) < 2:
                names = {m["name"]: m["role"] for m in _until(host, "presence")["members"]}
            assert names == {"admin": "host", "freundin": "guest"}

            # Play from 12 s: the friend follows, the host doesn't get an echo.
            host.send_json({"type": "sync", "action": "play", "position": 12})
            sync = _until(guest, "sync")
            assert sync["action"] == "play" and sync["paused"] is False and sync["by"] == "admin"
            assert 12 <= sync["position"] < 13

            # Anyone may pause or seek; nonsense is ignored.
            guest.send_json({"type": "sync", "action": "seek", "position": -3})
            guest.send_json({"type": "sync", "action": "explode", "position": 1})
            guest.send_json({"type": "sync", "action": "pause", "position": 40})
            paused = _until(host, "sync")
            assert paused["action"] == "pause" and paused["position"] == 40 and paused["paused"]

        # Someone joining later starts where the room is.
        with friend.websocket_connect(f"/api/party/{room['id']}") as late:
            state = _until(late, "joined")
            assert state["paused"] is True and state["position"] == 40


def test_ticks_keep_players_together(
    admin: TestClient, videos: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(party, "HEARTBEAT_S", 0.05)
    room = admin.post("/api/party", json={"video_id": videos["grown"]}).json()
    with admin.websocket_connect(f"/api/party/{room['id']}") as host:
        _until(host, "joined")
        host.send_json({"type": "sync", "action": "play", "position": 100})
        time.sleep(0.3)
        tick = _until(host, "tick")
        # Playing: the room's clock moved on by itself.
        assert tick["paused"] is False and tick["position"] > 100


def test_only_who_may_see_the_video(admin: TestClient, videos: dict[str, int]) -> None:
    kid = _login(admin, "kind", channel_access="selected", channel_ids=[videos["kids_channel"]])
    # Creating a room for a hidden video is refused like the video itself.
    assert kid.post("/api/party", json={"video_id": videos["grown"]}).status_code == 404
    grown_room: dict[str, Any] = admin.post("/api/party", json={"video_id": videos["grown"]}).json()
    with kid.websocket_connect(f"/api/party/{grown_room['id']}") as socket:
        assert "nicht freigegeben" in _until(socket, "closed")["reason"]
    with kid.websocket_connect("/api/party/nosuchroom") as socket:
        assert _until(socket, "closed")["reason"]
    # The kids video is fine for both.
    kids_room = kid.post("/api/party", json={"video_id": videos["kids"]}).json()
    with admin.websocket_connect(f"/api/party/{kids_room['id']}") as socket:
        assert _until(socket, "joined")["video_id"] == videos["kids"]


def test_one_account_cant_take_all_rooms() -> None:
    rooms = Rooms()
    first = rooms.create("party", owner_id=1, video_id=1)
    for _ in range(MAX_PER_OWNER - 1):
        rooms.create("party", owner_id=1, video_id=1)
    # One more: the oldest unused room makes way.
    rooms.create("party", owner_id=1, video_id=1)
    assert rooms.get(first.id) is None and rooms.count == MAX_PER_OWNER
    # All in use: refused – others can still open rooms.
    for room in list(rooms._rooms.values()):
        room.members.append(Member(user_id=1, username="a", role="host"))
    with pytest.raises(RoomError):
        rooms.create("party", owner_id=1, video_id=1)
    assert rooms.create("party", owner_id=2, video_id=1).owner_id == 2
