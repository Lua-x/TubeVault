from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.services import casting
from tests.conftest import HEADERS, VIDEO_BYTES, add_and_wait
from tests.test_playback import _library_video, needs_ffmpeg


def _path(url: str) -> str:
    return url.split("testserver", 1)[1]


def _video(admin: TestClient, youtube_id: str) -> int:
    add_and_wait(admin, youtube_id)
    return int(admin.get("/api/videos", params={"q": youtube_id}).json()["items"][0]["id"])


def test_signed_link_plays_without_login(admin: TestClient) -> None:
    vid = _video(admin, "castvideo01")
    response = admin.post(f"/api/videos/{vid}/cast")
    assert response.status_code == 200, response.text
    link = response.json()
    assert "/api/cast/" in link["url"] and link["url"].endswith(".mp4")
    assert link["url"].endswith("/api/" + link["path"])

    tv = TestClient(admin.app)  # the TV has no cookie
    response = tv.get(_path(link["url"]))
    assert response.status_code == 200 and response.content == VIDEO_BYTES
    assert response.headers["content-type"] == "video/mp4"
    assert tv.head(_path(link["url"])).status_code == 200
    partial = tv.get(_path(link["url"]), headers={"Range": "bytes=0-9"})
    assert partial.status_code == 206 and len(partial.content) == 10

    # Changing anything in the link breaks the signature.
    user_id, video_id, expires, signature = _path(link["url"]).split("/")[3:7]
    forged = [
        f"/api/cast/{user_id}/{video_id}/{int(expires) + 3600}/{signature}",
        f"/api/cast/{user_id}/{int(video_id) + 1}/{expires}/{signature}",
        f"/api/cast/{int(user_id) + 1}/{video_id}/{expires}/{signature}",
        f"/api/cast/{user_id}/{video_id}/{expires}/{'0' * 32}.mp4",
    ]
    for path in forged:
        assert tv.get(path).status_code == 404, path


def test_links_expire() -> None:
    """The signing itself, with a stand-in for the database row that keeps the key."""
    from app.models import Setting

    store: dict[str, Setting] = {}

    class FakeSession:
        def get(self, _model: object, key: str) -> Setting | None:
            return store.get(key)

        def add(self, row: Setting) -> None:
            store[row.key] = row

        def commit(self) -> None:
            pass

    db = FakeSession()
    now = time.time()
    expires, signature = casting.sign(db, 1, 2, now=now)  # type: ignore[arg-type]
    assert casting.verify(db, 1, 2, expires, signature, now=now + 60)  # type: ignore[arg-type]
    assert not casting.verify(db, 1, 2, expires, signature, now=expires + 1)  # type: ignore[arg-type]
    assert not casting.verify(db, 1, 3, expires, signature, now=now)  # type: ignore[arg-type]


def test_rights_are_checked_when_the_tv_asks(admin: TestClient) -> None:
    vid = _video(admin, "castrights1")
    channel = admin.get("/api/channels").json()[0]["id"]
    created = admin.post(
        "/api/users", json={"username": "gast", "password": "passwort1", "channel_access": "all"}
    ).json()
    guest = TestClient(admin.app, headers=HEADERS)
    guest.post("/api/auth/login", json={"username": "gast", "password": "passwort1"})
    response = guest.post(f"/api/videos/{vid}/cast")
    assert response.status_code == 200, response.text
    link = response.json()
    tv = TestClient(admin.app)
    assert tv.get(_path(link["url"])).status_code == 200

    # The account loses the channel: its old link stops working too.
    admin.patch(
        f"/api/users/{created['id']}",
        json={"channel_access": "selected", "channel_ids": [channel + 1000]},
    )
    assert tv.get(_path(link["url"])).status_code == 404


@needs_ffmpeg
def test_mkv_is_repacked_for_the_tv(admin: TestClient) -> None:
    vid = _library_video(admin, "castmkv0001", suffix=".mkv")
    link = admin.post(f"/api/videos/{vid}/cast").json()
    response = TestClient(admin.app).get(_path(link["url"]))
    assert response.status_code == 200 and response.headers["content-type"] == "video/mp4"
    assert response.content[4:8] == b"ftyp"  # an MP4 now
