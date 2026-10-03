from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import HEADERS, add_and_wait


def _video_id(client: TestClient, youtube_id: str) -> int:
    return int(client.get("/api/videos", params={"q": youtube_id}).json()["items"][0]["id"])


def _later(client: TestClient) -> dict:  # type: ignore[type-arg]
    return client.get("/api/playlists/watch-later").json()  # type: ignore[no-any-return]


def test_watch_later_is_a_fixed_playlist(admin: TestClient) -> None:
    add_and_wait(admin, "later000001")
    vid = _video_id(admin, "later000001")
    later = _later(admin)
    assert later["is_watch_later"] is True and later["name"] == "Später ansehen"
    assert later["videos"] == []
    assert _later(admin)["id"] == later["id"]  # one per user

    admin.post("/api/playlists", json={"name": "Eigene"})
    playlists = admin.get("/api/playlists").json()
    assert playlists[0]["id"] == later["id"]  # always first
    assert [p["is_watch_later"] for p in playlists] == [True, False]

    assert (
        admin.post(f"/api/playlists/{later['id']}/items", json={"video_id": vid}).status_code == 201
    )
    assert [v["id"] for v in _later(admin)["videos"]] == [vid]
    assert [v["id"] for v in admin.get("/api/home").json()["watch_later"]] == [vid]

    assert admin.patch(f"/api/playlists/{later['id']}", json={"name": "Anders"}).status_code == 400
    assert admin.delete(f"/api/playlists/{later['id']}").status_code == 400


def test_watched_videos_leave_the_list(admin: TestClient) -> None:
    for youtube_id in ("watched0001", "watched0002", "watched0003"):
        add_and_wait(admin, youtube_id)
    one, two, three = (_video_id(admin, y) for y in ("watched0001", "watched0002", "watched0003"))
    later = _later(admin)["id"]
    for vid in (one, two, three):
        admin.post(f"/api/playlists/{later}/items", json={"video_id": vid})

    # Played to the end (the test videos are 120 s long) …
    admin.put(f"/api/videos/{one}/progress", json={"position_s": 118, "duration_s": 120})
    # … or marked as watched.
    admin.put(f"/api/videos/{two}/watched", json={"watched": True})
    assert [v["id"] for v in _later(admin)["videos"]] == [three]

    # Watching again what is already watched doesn't throw a re-added video out.
    admin.post(f"/api/playlists/{later}/items", json={"video_id": one})
    admin.put(f"/api/videos/{one}/progress", json={"position_s": 30, "duration_s": 120})
    admin.put(f"/api/videos/{one}/progress", json={"position_s": 119, "duration_s": 120})
    assert {v["id"] for v in _later(admin)["videos"]} == {one, three}

    # Or keep everything, if that's what the user wants.
    admin.put("/api/auth/me/preferences", json={"watch_later_keep_watched": True})
    admin.put(f"/api/videos/{three}/watched", json={"watched": True})
    assert {v["id"] for v in _later(admin)["videos"]} == {one, three}


def test_watch_later_is_per_user(admin: TestClient) -> None:
    add_and_wait(admin, "peruser0001")
    vid = _video_id(admin, "peruser0001")
    admin.post(f"/api/playlists/{_later(admin)['id']}/items", json={"video_id": vid})
    admin.post("/api/users", json={"username": "zweiter", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "zweiter", "password": "passwort1"})
    assert _later(other)["videos"] == [] and _later(other)["id"] != _later(admin)["id"]
    assert other.get(f"/api/playlists/{_later(admin)['id']}").status_code == 404


def test_history(admin: TestClient) -> None:
    for youtube_id in ("history0001", "history0002", "history0003"):
        add_and_wait(admin, youtube_id)
    one, two, three = (_video_id(admin, y) for y in ("history0001", "history0002", "history0003"))
    assert admin.get("/api/history").json() == {"items": [], "total": 0}

    admin.put(f"/api/videos/{one}/progress", json={"position_s": 20})
    admin.put(f"/api/videos/{two}/watched", json={"watched": True})
    admin.put(f"/api/videos/{three}/progress", json={"position_s": 40})
    page = admin.get("/api/history").json()
    assert page["total"] == 3
    assert [v["id"] for v in page["items"]] == [three, two, one]  # newest first
    assert [
        v["id"] for v in admin.get("/api/history", params={"limit": 1, "offset": 1}).json()["items"]
    ] == [two]

    # "Mark as unwatched" resets the position – then it's no longer in the history.
    admin.put(f"/api/videos/{two}/watched", json={"watched": False})
    assert [v["id"] for v in admin.get("/api/history").json()["items"]] == [three, one]

    assert admin.delete(f"/api/history/{three}").status_code == 204
    assert [v["id"] for v in admin.get("/api/history").json()["items"]] == [one]
    assert admin.get(f"/api/videos/{three}").json()["progress"] is None
    assert admin.delete("/api/history").status_code == 204
    assert admin.get("/api/history").json()["total"] == 0
