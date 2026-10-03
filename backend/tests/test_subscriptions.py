from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.models import SubscriptionKind
from app.services.catalog import Entry, entry_from_info, sort_newest_first
from app.services.youtube_urls import InvalidVideoUrlError, parse_source_url
from tests.conftest import (
    HEADERS,
    FakeCatalog,
    FakeDownloader,
    add_and_wait,
    job_status,
    wait_for,
)

TODAY = date.today()


def entry(n: int, **kwargs: Any) -> Entry:
    """Video n, uploaded n days ago (so lower numbers are newer)."""
    values: dict[str, Any] = {
        "youtube_id": f"vid{n:08d}",
        "title": f"Video {n}",
        "duration_s": 600,
        "upload_date": TODAY - timedelta(days=n),
    }
    values.update(kwargs)
    return Entry(**values)


def subscribe(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/subscriptions", json={"url": "@test", **body})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def detail(client: TestClient, sub_id: int) -> dict[str, Any]:
    return client.get(f"/api/subscriptions/{sub_id}").json()  # type: ignore[no-any-return]


def wait_checked(client: TestClient, sub_id: int, after: str | None = None) -> dict[str, Any]:
    def checked() -> dict[str, Any] | None:
        sub = detail(client, sub_id)
        done = sub["last_checked_at"] and sub["last_checked_at"] != after and not sub["checking"]
        return sub if done or sub["last_check_error"] else None

    result: dict[str, Any] = wait_for(checked)
    return result


def wait_idle(client: TestClient) -> None:
    def idle() -> bool:
        jobs = client.get("/api/downloads").json()["items"]
        return all(j["status"] not in ("queued", "running") for j in jobs)

    wait_for(idle)


def states(sub: dict[str, Any]) -> dict[str, str]:
    return {item["youtube_id"]: item["state"] for item in sub["items"]}


# --- URL parsing and listing helpers ------------------------------------------------


@pytest.mark.parametrize(
    ("url", "kind", "expected"),
    [
        ("@kanal", SubscriptionKind.CHANNEL, "https://www.youtube.com/@kanal"),
        (
            "https://www.youtube.com/@kanal/videos",
            SubscriptionKind.CHANNEL,
            "https://www.youtube.com/@kanal",
        ),
        (
            "youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ",
            SubscriptionKind.CHANNEL,
            "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ",
        ),
        (
            "https://youtube.com/c/Foo/shorts",
            SubscriptionKind.CHANNEL,
            "https://www.youtube.com/c/Foo",
        ),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG",
            SubscriptionKind.PLAYLIST,
            "https://www.youtube.com/playlist?list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG",
        ),
    ],
)
def test_parse_source_url(url: str, kind: SubscriptionKind, expected: str) -> None:
    assert parse_source_url(url) == (kind, expected)


@pytest.mark.parametrize(
    "url", ["https://vimeo.com/x", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
)
def test_parse_source_url_rejects(url: str) -> None:
    with pytest.raises(InvalidVideoUrlError):
        parse_source_url(url)


def test_entry_from_flat_info() -> None:
    short = entry_from_info(
        {"id": "abc", "url": "https://www.youtube.com/shorts/abc", "duration": 30, "timestamp": 0}
    )
    assert short is not None and short.is_short and short.upload_date == date(1970, 1, 1)
    stream = entry_from_info({"id": "def", "title": "Live"}, tab="streams")
    assert stream is not None and stream.live_status == "was_live"
    private = entry_from_info({"id": "ghi", "title": "[Private video]"})
    assert private is not None and private.unavailable
    assert entry_from_info({"title": "no id"}) is None


def test_sort_newest_first_keeps_order_without_dates() -> None:
    a, b, c = entry(5), entry(1), entry(3, upload_date=None)
    assert [e.youtube_id for e in sort_newest_first([a, c, b])] == [
        b.youtube_id,
        a.youtube_id,
        c.youtube_id,
    ]


# --- subscribing and checking ------------------------------------------------------------


def test_subscribe_takes_newest_videos_and_filters(
    admin: TestClient, catalog: FakeCatalog, settings: Settings
) -> None:
    catalog.entries = [
        entry(1),
        entry(2),
        entry(3, duration_s=30),  # too short
        entry(4),
        entry(5, title="[Private video]", unavailable=True),
        entry(6, live_status="is_upcoming"),  # not downloadable yet
        entry(7),
    ]
    sub = subscribe(admin, backfill=2, min_duration_s=120)
    assert sub["title"] == "Test Channel" and sub["kind"] == "channel"

    sub = wait_checked(admin, sub["id"])
    seen = {key: "queued" if value == "downloaded" else value for key, value in states(sub).items()}
    assert seen == {
        "vid00000001": "queued",
        "vid00000002": "queued",
        "vid00000003": "filtered",
        "vid00000004": "skipped",
        "vid00000005": "filtered",
        "vid00000007": "skipped",
    }
    reasons = {i["youtube_id"]: i["reason"] for i in sub["items"]}
    assert reasons["vid00000003"] == "Kürzer als 2 min"

    wait_idle(admin)
    sub = detail(admin, sub["id"])
    assert sub["stats"]["downloaded"] == 2
    assert sub["channel"]["has_avatar"] is True
    assert (settings.media_dir / "Test Channel" / "folder.jpg").is_file()
    avatar = admin.get(f"/api/channels/{sub['channel']['id']}/avatar")
    assert avatar.status_code == 200

    # Library and queue know where the videos came from.
    jobs = admin.get("/api/downloads").json()["items"]
    assert {j["subscription"]["title"] for j in jobs} == {"Test Channel"}
    assert admin.get("/api/videos").json()["total"] == 2


def test_next_check_only_takes_new_videos(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(2), entry(3)]
    sub = wait_checked(admin, subscribe(admin, backfill=1)["id"])
    wait_idle(admin)
    first_check = sub["last_checked_at"]

    catalog.entries = [entry(0), entry(1), entry(2), entry(3)]
    assert admin.post(f"/api/subscriptions/{sub['id']}/check").status_code == 202
    sub = wait_checked(admin, sub["id"], after=first_check)
    seen = states(sub)
    assert seen["vid00000003"] == "skipped"
    assert {seen["vid00000000"], seen["vid00000001"]} <= {"queued", "downloaded"}
    wait_idle(admin)
    assert detail(admin, sub["id"])["stats"]["downloaded"] == 3


def test_shorts_tab_only_when_enabled(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(1), entry(2, is_short=True, duration_s=40)]
    wait_checked(admin, subscribe(admin, backfill=None)["id"])
    assert catalog.calls[-1][1] == ("videos",)

    playlist = "https://www.youtube.com/playlist?list=PLtestplaylist01"
    other = admin.post(
        "/api/subscriptions",
        json={"url": playlist, "include_shorts": True, "include_live": True, "backfill": None},
    )
    assert other.status_code == 201
    wait_checked(admin, other.json()["id"])
    assert catalog.calls[-1][2] is not None  # playlists are capped


def test_filter_after_metadata(
    admin: TestClient, catalog: FakeCatalog, downloader: FakeDownloader
) -> None:
    """The listing can't always tell shorts or exact dates; the job checks again."""
    catalog.entries = [entry(1), entry(2)]
    downloader.meta_overrides["vid00000001"] = {"is_short": True}
    downloader.meta_overrides["vid00000002"] = {"upload_date": date(2020, 1, 1)}
    sub = subscribe(admin, backfill=None, date_after="2023-01-01")
    wait_checked(admin, sub["id"])
    wait_idle(admin)
    sub = detail(admin, sub["id"])
    assert states(sub) == {"vid00000001": "filtered", "vid00000002": "filtered"}
    jobs = admin.get("/api/downloads").json()["items"]
    assert {j["status"] for j in jobs} == {"skipped"}
    assert {j["error_message"] for j in jobs} == {
        "Shorts ausgeschlossen",
        "Vor dem 01.01.2023 hochgeladen",
    }
    assert admin.get("/api/videos").json()["total"] == 0


def test_existing_video_is_linked_not_downloaded_again(
    admin: TestClient, catalog: FakeCatalog, downloader: FakeDownloader
) -> None:
    add_and_wait(admin, "vid00000001")
    catalog.entries = [entry(1)]
    sub = wait_checked(admin, subscribe(admin)["id"])
    assert states(sub) == {"vid00000001": "downloaded"}
    assert downloader.downloads == 1


def test_duplicate_and_invalid(admin: TestClient, catalog: FakeCatalog) -> None:
    subscribe(admin)
    assert admin.post("/api/subscriptions", json={"url": "@test"}).status_code == 409
    assert admin.post("/api/subscriptions", json={"url": "https://vimeo.com/x"}).status_code == 400
    bad = admin.post(
        "/api/subscriptions",
        json={"url": "@other", "min_duration_s": 600, "max_duration_s": 60},
    )
    assert bad.status_code == 422
    catalog.error = Exception("ERROR: [youtube:tab] @nope: This channel does not exist.")
    assert admin.post("/api/subscriptions", json={"url": "@nope"}).status_code == 502


def test_check_errors_are_recorded(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.list_error = ConnectionError("Connection reset by peer")
    sub = wait_checked(admin, subscribe(admin)["id"])
    assert "Connection reset" in sub["last_check_error"]
    assert sub["last_checked_at"] is None


def test_update_and_reevaluate(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(1, is_short=True, duration_s=30)]
    sub = wait_checked(admin, subscribe(admin, include_shorts=True, max_duration_s=20)["id"])
    assert states(sub) == {"vid00000001": "filtered"}

    settings = {key: sub[key] for key in (
        "enabled", "check_interval_minutes", "include_shorts", "include_live", "min_duration_s",
        "date_after", "keep_days", "keep_last", "download_options")}  # fmt: skip
    settings["max_duration_s"] = None
    settings["download_options"] = {"container": "mkv"}
    updated = admin.put(f"/api/subscriptions/{sub['id']}", json=settings)
    assert updated.status_code == 200
    assert updated.json()["download_options"]["container"] == "mkv"

    before = sub["last_checked_at"]
    admin.post(f"/api/subscriptions/{sub['id']}/reevaluate")
    sub = wait_checked(admin, sub["id"], after=before)
    wait_idle(admin)
    assert states(detail(admin, sub["id"])) == {"vid00000001": "downloaded"}
    video = admin.get("/api/videos").json()["items"][0]
    assert admin.get(f"/api/videos/{video['id']}").json()["container"] == "mkv"


# --- cleanup ------------------------------------------------------------------------------


def test_keep_last_cleans_up_but_keeps_manual_videos(
    admin: TestClient, catalog: FakeCatalog, downloader: FakeDownloader
) -> None:
    for n in range(1, 5):
        downloader.meta_overrides[f"vid{n:08d}"] = {"upload_date": TODAY - timedelta(days=n)}
    add_and_wait(admin, "vid00000004")  # added by hand before subscribing
    catalog.entries = [entry(1), entry(2), entry(3), entry(4)]
    sub = wait_checked(admin, subscribe(admin, backfill=None)["id"])
    wait_idle(admin)
    assert detail(admin, sub["id"])["stats"]["downloaded"] == 4

    settings = {key: sub[key] for key in (
        "enabled", "check_interval_minutes", "include_shorts", "include_live", "min_duration_s",
        "max_duration_s", "date_after", "keep_days", "download_options")}  # fmt: skip
    settings["keep_last"] = 2
    admin.put(f"/api/subscriptions/{sub['id']}", json=settings)

    wait_for(lambda: admin.get("/api/videos").json()["total"] == 3)
    titles = {v["youtube_id"] for v in admin.get("/api/videos").json()["items"]}
    assert titles == {"vid00000001", "vid00000002", "vid00000004"}
    sub = detail(admin, sub["id"])
    assert states(sub)["vid00000003"] == "removed"
    assert {i["reason"] for i in sub["items"] if i["state"] == "removed"} == {
        "Automatisch aufgeräumt"
    }


def test_keep_days_limits_new_downloads(
    admin: TestClient, catalog: FakeCatalog, downloader: FakeDownloader
) -> None:
    downloader.meta_overrides["vid00000001"] = {"upload_date": TODAY - timedelta(days=1)}
    catalog.entries = [entry(1), entry(40)]
    sub = wait_checked(admin, subscribe(admin, backfill=None, keep_days=14)["id"])
    seen = states(sub)
    assert seen["vid00000040"] == "filtered"
    assert seen["vid00000001"] in ("queued", "downloaded")
    wait_idle(admin)
    assert states(detail(admin, sub["id"]))["vid00000001"] == "downloaded"


def test_delete_subscription_with_videos(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(1), entry(2)]
    sub = wait_checked(admin, subscribe(admin, backfill=None)["id"])
    wait_idle(admin)
    add_and_wait(admin, "manual00001")
    response = admin.delete(f"/api/subscriptions/{sub['id']}", params={"delete_videos": True})
    assert response.status_code == 204
    assert admin.get("/api/subscriptions").json() == []
    remaining = admin.get("/api/videos").json()["items"]
    assert [v["youtube_id"] for v in remaining] == ["manual00001"]


def test_deleted_video_is_not_downloaded_again(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(1)]
    sub = wait_checked(admin, subscribe(admin)["id"])
    wait_idle(admin)
    video_id = admin.get("/api/videos").json()["items"][0]["id"]
    admin.delete(f"/api/videos/{video_id}")
    before = detail(admin, sub["id"])["last_checked_at"]
    admin.post(f"/api/subscriptions/{sub['id']}/check")
    sub = wait_checked(admin, sub["id"], after=before)
    assert states(sub) == {"vid00000001": "removed"}
    assert admin.get("/api/videos").json()["total"] == 0


# --- queue control ------------------------------------------------------------------------


def test_pause_and_resume_job(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.gate = threading.Event()
    job_id = admin.post("/api/videos", json={"url": "https://youtu.be/pausepause1"}).json()["id"]
    assert downloader.started.wait(5)
    assert admin.post(f"/api/downloads/{job_id}/pause").status_code == 200
    wait_for(lambda: job_status(admin, job_id) == "paused")

    downloader.gate.set()
    assert admin.post(f"/api/downloads/{job_id}/resume").status_code == 200
    wait_for(lambda: job_status(admin, job_id) == "completed")


def test_pause_all_holds_the_queue(admin: TestClient) -> None:
    state = admin.post("/api/downloads/pause-all").json()
    assert state["paused"] is True
    job_id = admin.post("/api/videos", json={"url": "https://youtu.be/heldheld001"}).json()["id"]
    time.sleep(0.5)
    assert job_status(admin, job_id) == "queued"
    assert admin.get("/api/downloads/state").json()["paused"] is True

    assert admin.post("/api/downloads/resume-all").json()["paused"] is False
    wait_for(lambda: job_status(admin, job_id) == "completed")


def test_retry_failed(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.errors.append(Exception("ERROR: Video unavailable"))
    job = add_and_wait(admin, "failfail001")
    assert job["status"] == "failed"
    assert admin.post("/api/downloads/retry-failed").status_code == 200
    wait_for(lambda: job_status(admin, job["id"]) == "completed")


def test_only_admins_set_cleanup_rules(admin: TestClient) -> None:
    admin.post("/api/users", json={"username": "lena", "password": "passwort1"})
    user = TestClient(admin.app, headers=HEADERS)
    user.post("/api/auth/login", json={"username": "lena", "password": "passwort1"})

    denied = user.post("/api/subscriptions", json={"url": "@test", "keep_last": 1})
    assert denied.status_code == 403 and "Administratoren" in denied.json()["detail"]
    sub = subscribe(user)
    body = {**user.get(f"/api/subscriptions/{sub['id']}").json(), "include_shorts": True}
    assert user.put(f"/api/subscriptions/{sub['id']}", json=body).status_code == 200
    stricter = {**body, "keep_days": 7}
    assert user.put(f"/api/subscriptions/{sub['id']}", json=stricter).status_code == 403
    assert admin.put(f"/api/subscriptions/{sub['id']}", json=stricter).status_code == 200
