from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.services.downloader import comments_from_info
from tests.conftest import HEADERS, FakeCatalog, FakeDownloader, add_and_wait, wait_for
from tests.test_subscriptions import entry


def _video_id(client: TestClient, youtube_id: str) -> int:
    items = client.get("/api/videos", params={"q": youtube_id}).json()["items"]
    return int(items[0]["id"])


def _enable(admin: TestClient, **downloads: Any) -> None:
    current = admin.get("/api/settings").json()
    current["downloads"] |= downloads
    assert admin.put("/api/settings", json=current).status_code == 200


def test_comments_are_off_unless_wanted(admin: TestClient, downloader: FakeDownloader) -> None:
    add_and_wait(admin, "nocomment01")
    vid = _video_id(admin, "nocomment01")
    page = admin.get(f"/api/videos/{vid}/comments").json()
    assert page["items"] == [] and page["fetched_at"] is None and page["fetching"] is False
    assert downloader.comment_calls == []
    assert admin.get(f"/api/videos/{vid}").json()["comment_count"] is None


def test_comments_saved_with_the_download(admin: TestClient, downloader: FakeDownloader) -> None:
    _enable(admin, comments=True, max_comments=100)
    add_and_wait(admin, "comments001")
    vid = _video_id(admin, "comments001")
    wait_for(lambda: admin.get(f"/api/videos/{vid}/comments").json()["fetched_at"])
    assert downloader.comment_calls == [("https://www.youtube.com/watch?v=comments001", 100)]

    page = admin.get(f"/api/videos/{vid}/comments").json()
    assert page["total"] == 3 and page["saved"] == 4 and page["comment_count"] == 1234
    # Pinned first, then YouTube's order; replies hang under their comment.
    assert [c["author"] for c in page["items"]] == ["Cleo", "Anna", "Ben"]
    anna = page["items"][1]
    assert [r["text"] for r in anna["replies"]] == ["Danke!"]
    assert anna["replies"][0]["author_is_uploader"] is True
    assert anna["replies"][0]["author_is_verified"] is True

    newest = admin.get(f"/api/videos/{vid}/comments", params={"sort": "new"}).json()
    assert [c["author"] for c in newest["items"]] == ["Ben", "Anna", "Cleo"]
    second = admin.get(f"/api/videos/{vid}/comments", params={"offset": 2, "limit": 2}).json()
    assert [c["author"] for c in second["items"]] == ["Ben"]
    assert admin.get(f"/api/videos/{vid}").json()["comment_count"] == 1234


def test_per_video_choice_beats_the_setting(admin: TestClient, downloader: FakeDownloader) -> None:
    response = admin.post(
        "/api/videos", json={"url": "https://youtu.be/pervideo001", "comments": True}
    )
    assert response.status_code == 202
    wait_for(lambda: downloader.comment_calls)
    _enable(admin, comments=True)
    response = admin.post(
        "/api/videos", json={"url": "https://youtu.be/pervideo002", "comments": False}
    )
    job_id = response.json()["id"]
    wait_for(
        lambda: (
            next(j for j in admin.get("/api/downloads").json()["items"] if j["id"] == job_id)[
                "status"
            ]
            == "completed"
        )
    )
    assert [url for url, _ in downloader.comment_calls] == [
        "https://www.youtube.com/watch?v=pervideo001"
    ]


def test_load_later_refresh_and_delete(admin: TestClient, downloader: FakeDownloader) -> None:
    add_and_wait(admin, "later000001")
    vid = _video_id(admin, "later000001")
    assert admin.post(f"/api/videos/{vid}/comments").status_code == 202
    wait_for(lambda: admin.get(f"/api/videos/{vid}/comments").json()["saved"] == 4)
    # Loading again replaces, it doesn't duplicate.
    admin.post(f"/api/videos/{vid}/comments")
    wait_for(lambda: len(downloader.comment_calls) == 2)
    wait_for(lambda: not admin.get(f"/api/videos/{vid}/comments").json()["fetching"])
    assert admin.get(f"/api/videos/{vid}/comments").json()["saved"] == 4

    assert admin.delete(f"/api/videos/{vid}/comments").status_code == 204
    page = admin.get(f"/api/videos/{vid}/comments").json()
    assert page["saved"] == 0 and page["fetched_at"] is None


def test_failure_is_reported_and_keeps_the_video(
    admin: TestClient, downloader: FakeDownloader
) -> None:
    add_and_wait(admin, "failing0001")
    vid = _video_id(admin, "failing0001")
    downloader.comment_error = RuntimeError("ERROR: [youtube] Comments are turned off")
    admin.post(f"/api/videos/{vid}/comments")
    page = wait_for(
        lambda: (
            admin.get(f"/api/videos/{vid}/comments").json()["error"]
            and admin.get(f"/api/videos/{vid}/comments").json()
        )
    )
    assert "Comments are turned off" in page["error"] and page["fetching"] is False
    assert admin.get(f"/api/videos/{vid}").json()["status"] == "ready"


def test_view_only_accounts_cannot_fetch(admin: TestClient) -> None:
    add_and_wait(admin, "viewonly001")
    vid = _video_id(admin, "viewonly001")
    created = admin.post(
        "/api/users", json={"username": "schauer", "password": "passwort1", "may_add": False}
    )
    assert created.status_code == 201
    viewer = TestClient(admin.app, headers=HEADERS)
    viewer.post("/api/auth/login", json={"username": "schauer", "password": "passwort1"})
    assert viewer.get(f"/api/videos/{vid}/comments").status_code == 200
    assert viewer.post(f"/api/videos/{vid}/comments").status_code == 403
    assert viewer.delete(f"/api/videos/{vid}/comments").status_code == 403


def test_comments_from_ytdlp_info() -> None:
    result = comments_from_info(
        {
            "comment_count": 2,
            "comments": [
                {"id": "a", "parent": "root", "text": "Hallo", "author": "X", "timestamp": 0},
                {"id": "b", "parent": "a", "text": "Hi", "author": "", "like_count": 3},
                {"text": "ohne ID"},
            ],
        }
    )
    assert result.total == 2
    assert [(c.youtube_id, c.parent_id, c.author) for c in result.comments] == [
        ("a", None, "X"),
        ("b", "a", "Unbekannt"),
    ]
    assert result.comments[0].published_at is not None
    assert result.comments[1].like_count == 3


def test_subscription_choice(
    admin: TestClient, downloader: FakeDownloader, catalog: FakeCatalog
) -> None:
    catalog.entries = [entry(1)]
    response = admin.post(
        "/api/subscriptions",
        json={"url": "@test", "backfill": 1, "download_options": {"comments": True}},
    )
    assert response.status_code == 201, response.text
    assert response.json()["download_options"]["comments"] is True
    wait_for(lambda: downloader.comment_calls, timeout=10)
    assert downloader.comment_calls[0][0].endswith("vid00000001")
