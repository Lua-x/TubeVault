from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.services.search import similar_query
from tests.conftest import FakeDownloader, add_and_wait


def _add(admin: TestClient, downloader: FakeDownloader, youtube_id: str, **meta: object) -> int:
    downloader.meta_overrides[youtube_id] = meta
    add_and_wait(admin, youtube_id)
    items = admin.get("/api/videos", params={"limit": 200}).json()["items"]
    return int(next(v["id"] for v in items if v["youtube_id"] == youtube_id))


def _ids(admin: TestClient, **params: object) -> list[int]:
    return [v["id"] for v in admin.get("/api/videos", params=params).json()["items"]]


def test_duration_and_upload_filters(admin: TestClient, downloader: FakeDownloader) -> None:
    today = date.today()
    short = _add(admin, downloader, "short000001", duration_s=60, upload_date=today)
    medium = _add(
        admin, downloader, "medium00001", duration_s=600, upload_date=today - timedelta(days=20)
    )
    long = _add(
        admin, downloader, "long0000001", duration_s=3600, upload_date=today - timedelta(days=400)
    )
    assert set(_ids(admin, duration="short")) == {short}
    assert set(_ids(admin, duration="medium")) == {medium}
    assert set(_ids(admin, duration="long")) == {long}
    assert set(_ids(admin, uploaded="week")) == {short}
    assert set(_ids(admin, uploaded="month")) == {short, medium}
    assert set(_ids(admin, uploaded="year")) == {short, medium}
    assert set(_ids(admin, uploaded="month", duration="medium")) == {medium}
    assert admin.get("/api/videos", params={"duration": "huge"}).status_code == 422


def test_similar_videos(admin: TestClient, downloader: FakeDownloader) -> None:
    ssd = _add(admin, downloader, "similar0001", title="Warum SSDs langsamer werden")
    trim = _add(admin, downloader, "similar0002", title="SSD TRIM richtig einrichten")
    nvme = _add(admin, downloader, "similar0003", title="Die schnellsten SSDs 2026 im Test")
    _add(
        admin,
        downloader,
        "similar0004",
        title="Pasta wie in Rom",
        channel_id="UCkochen",
        channel_name="Küche am Abend",
    )

    similar = [v["id"] for v in admin.get(f"/api/videos/{ssd}/similar").json()]
    assert ssd not in similar
    # Videos sharing "ssds" come first; the rest of the channel fills up – not the pasta.
    assert similar[0] == nvme and set(similar) == {nvme, trim}
    assert len(admin.get(f"/api/videos/{ssd}/similar", params={"limit": 1}).json()) == 1
    assert admin.get("/api/videos/99999/similar").status_code == 404


def test_similar_query() -> None:
    assert similar_query("Die 10 besten Tipps für den Garten – Teil 2") == (
        '"besten" OR "tipps" OR "garten"'
    )
    assert similar_query("Das ist es") is None
