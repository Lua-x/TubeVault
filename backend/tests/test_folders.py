"""Each account's own folders: folders inside folders, a video in several, nothing shared."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.test_access import _login, library  # noqa: F401 – fixture


def _folder(client: TestClient, name: str, parent_id: int | None = None) -> dict[str, Any]:
    response = client.post("/api/folders", json={"name": name, "parent_id": parent_id})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_folders_inside_folders(admin: TestClient, library: dict[str, Any]) -> None:  # noqa: F811
    cooking = _folder(admin, "  Kochen ")
    baking = _folder(admin, "Backen", cooking["id"])
    bread = _folder(admin, "Brot", baking["id"])
    assert (cooking["name"], baking["parent_id"]) == ("Kochen", cooking["id"])

    folders = {f["name"]: f for f in admin.get("/api/folders").json()}
    assert folders["Kochen"]["folder_count"] == 1
    assert folders["Brot"]["parent_id"] == baking["id"]

    detail = admin.get(f"/api/folders/{bread['id']}").json()
    assert [c["name"] for c in detail["path"]] == ["Kochen", "Backen"]
    assert detail["folders"] == [] and detail["videos"] == []

    # Same name next to each other: no; somewhere else: fine.
    assert admin.post("/api/folders", json={"name": "kochen"}).status_code == 409
    _folder(admin, "Kochen", bread["id"])
    assert admin.post("/api/folders", json={"name": "  "}).status_code == 422
    assert admin.post("/api/folders", json={"name": "X", "parent_id": 99999}).status_code == 404


def test_videos_in_folders(admin: TestClient, library: dict[str, Any]) -> None:  # noqa: F811
    video = library["kids_video"]
    first, second = _folder(admin, "Für Mia"), _folder(admin, "Lieblinge")
    for folder in (first, second):  # one video, two folders
        added = admin.put(f"/api/folders/{folder['id']}/videos/{video}").json()
        assert (added["video_count"], added["contains"]) == (1, True)
    again = admin.put(f"/api/folders/{first['id']}/videos/{video}").json()
    assert again["video_count"] == 1  # no duplicates

    marked = {f["name"]: f["contains"] for f in admin.get(f"/api/folders?video_id={video}").json()}
    assert marked == {"Für Mia": True, "Lieblinge": True}
    detail = admin.get(f"/api/folders/{first['id']}").json()
    assert [v["id"] for v in detail["videos"]] == [video]
    assert len(detail["cover"]) == 1

    removed = admin.delete(f"/api/folders/{second['id']}/videos/{video}").json()
    assert (removed["video_count"], removed["contains"]) == (0, False)
    assert admin.put(f"/api/folders/{first['id']}/videos/99999").status_code == 404

    # Deleting the video takes it out of every folder.
    admin.delete(f"/api/videos/{video}")
    assert admin.get(f"/api/folders/{first['id']}").json()["videos"] == []


def test_rename_move_and_delete(admin: TestClient, library: dict[str, Any]) -> None:  # noqa: F811
    top = _folder(admin, "Oben")
    middle = _folder(admin, "Mitte", top["id"])
    bottom = _folder(admin, "Unten", middle["id"])
    admin.put(f"/api/folders/{bottom['id']}/videos/{library['other_video']}")

    renamed = admin.patch(f"/api/folders/{middle['id']}", json={"name": "Mittendrin"}).json()
    assert (renamed["name"], renamed["parent_id"]) == ("Mittendrin", top["id"])  # stays put

    # Never into itself or below itself.
    url = f"/api/folders/{top['id']}"
    for target in (top["id"], bottom["id"]):
        assert admin.patch(url, json={"parent_id": target}).status_code == 400

    moved = admin.patch(f"/api/folders/{bottom['id']}", json={"parent_id": None}).json()
    assert moved["parent_id"] is None
    back = admin.patch(f"/api/folders/{bottom['id']}", json={"parent_id": middle["id"]}).json()
    assert back["parent_id"] == middle["id"]

    # Deleting a folder takes the folders inside along; the videos stay in the library.
    assert admin.delete(url).status_code == 204
    assert admin.get("/api/folders").json() == []
    assert admin.get(f"/api/videos/{library['other_video']}").status_code == 200


def test_depth_is_limited(admin: TestClient, library: dict[str, Any]) -> None:  # noqa: F811
    parent: int | None = None
    for level in range(10):
        parent = _folder(admin, f"Ebene {level + 1}", parent)["id"]
    assert (
        admin.post("/api/folders", json={"name": "Zu tief", "parent_id": parent}).status_code == 400
    )


def test_folders_are_private(admin: TestClient, library: dict[str, Any]) -> None:  # noqa: F811
    mine = _folder(admin, "Meins")
    admin.put(f"/api/folders/{mine['id']}/videos/{library['kids_video']}")
    admin.put(f"/api/folders/{mine['id']}/videos/{library['other_video']}")
    kid = _login(admin, "kind", channel_access="selected", channel_ids=[library["kids_channel"]])

    assert kid.get("/api/folders").json() == []
    for request in (
        kid.get(f"/api/folders/{mine['id']}"),
        kid.patch(f"/api/folders/{mine['id']}", json={"name": "Geklaut"}),
        kid.delete(f"/api/folders/{mine['id']}"),
        kid.put(f"/api/folders/{mine['id']}/videos/{library['kids_video']}"),
        kid.post("/api/folders", json={"name": "Drin", "parent_id": mine["id"]}),
    ):
        assert request.status_code == 404

    # A kids profile has folders too – with only the videos it may see.
    own = _folder(kid, "Meine Videos")
    assert kid.put(f"/api/folders/{own['id']}/videos/{library['other_video']}").status_code == 404
    assert kid.put(f"/api/folders/{own['id']}/videos/{library['kids_video']}").status_code == 200
    # If an admin narrows the access later, hidden videos drop out of the folder.
    kid_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "kind")
    admin.patch(f"/api/users/{kid_id}", json={"channel_access": "selected", "channel_ids": []})
    assert kid.get(f"/api/folders/{own['id']}").json()["videos"] == []
