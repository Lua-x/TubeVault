from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import HEADERS, VIDEO_BYTES, add_and_wait


def _video_id(client: TestClient) -> int:
    add_and_wait(client)
    return int(client.get("/api/videos").json()["items"][0]["id"])


def test_stream_supports_range_requests(admin: TestClient) -> None:
    video_id = _video_id(admin)
    full = admin.get(f"/api/videos/{video_id}/stream")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-type"] == "video/mp4"
    assert full.content == VIDEO_BYTES

    partial = admin.get(f"/api/videos/{video_id}/stream", headers={"Range": "bytes=100-199"})
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 100-199/{len(VIDEO_BYTES)}"
    assert partial.content == VIDEO_BYTES[100:200]

    tail = admin.get(f"/api/videos/{video_id}/stream", headers={"Range": "bytes=-10"})
    assert tail.content == VIDEO_BYTES[-10:]


def test_media_requires_login(admin: TestClient) -> None:
    video_id = _video_id(admin)
    anonymous = TestClient(admin.app, headers=HEADERS)
    assert anonymous.get(f"/api/videos/{video_id}/stream").status_code == 401
    assert anonymous.get(f"/api/videos/{video_id}/thumbnail").status_code == 401


def test_thumbnail_subtitles_chapters(admin: TestClient) -> None:
    video_id = _video_id(admin)
    thumb = admin.get(f"/api/videos/{video_id}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"

    detail = admin.get(f"/api/videos/{video_id}").json()
    sub_id = detail["subtitles"][0]["id"]
    sub = admin.get(f"/api/videos/{video_id}/subtitles/{sub_id}.vtt")
    assert sub.status_code == 200
    assert sub.text.startswith("WEBVTT")
    assert admin.get(f"/api/videos/{video_id}/subtitles/999.vtt").status_code == 404

    chapters = admin.get(f"/api/videos/{video_id}/chapters.vtt")
    assert chapters.text.splitlines()[:5] == [
        "WEBVTT",
        "",
        "1",
        "00:00:00.000 --> 00:01:00.000",
        "Intro",
    ]


def test_system_info(admin: TestClient) -> None:
    _video_id(admin)
    info = admin.get("/api/system/info").json()
    assert info["video_count"] == 1
    assert info["library_size"] == len(VIDEO_BYTES)
    assert admin.get("/api/health").json() == {"status": "ok"}


def test_websocket_origin_check(admin: TestClient) -> None:
    from app.routers.ws import _hostname

    assert _hostname("Example.com:8096") == "example.com"
    assert _hostname("[::1]:8096") == "[::1]"
    with admin.websocket_connect(
        "/api/ws", headers={"Origin": "http://testserver:8096", "Host": "testserver"}
    ) as socket:
        socket.close()


def test_websocket_rejects_foreign_origin(admin: TestClient) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        admin.websocket_connect("/api/ws", headers={"Origin": "https://evil.example"}) as socket,
    ):
        socket.receive_json()
