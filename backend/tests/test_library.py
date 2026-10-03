from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import sponsorblock
from app.services.app_settings import DownloadOptions
from app.services.downloader import YtDlpDownloader
from app.services.search import fts_query
from app.services.sponsorblock import Segment, parse_response
from tests.conftest import HEADERS, FakeCatalog, FakeDownloader, add_and_wait, wait_for


def video_id(client: TestClient, youtube_id: str) -> int:
    videos = client.get("/api/videos", params={"limit": 200}).json()["items"]
    return int(next(v["id"] for v in videos if v["youtube_id"] == youtube_id))


# --- watch progress -----------------------------------------------------------------------


def test_progress_resume_and_watched(admin: TestClient) -> None:
    add_and_wait(admin, "progress001")
    vid = video_id(admin, "progress001")

    state = admin.put(f"/api/videos/{vid}/progress", json={"position_s": 42.5}).json()
    assert state == {"position_s": 42.5, "watched": False, "updated_at": state["updated_at"]}
    assert admin.get(f"/api/videos/{vid}").json()["progress"]["position_s"] == 42.5

    # Close to the end (duration 120 s) counts as watched.
    assert admin.put(f"/api/videos/{vid}/progress", json={"position_s": 115}).json()["watched"]
    # Re-watching a part keeps it watched.
    assert admin.put(f"/api/videos/{vid}/progress", json={"position_s": 50}).json()["watched"]
    unwatched = admin.put(f"/api/videos/{vid}/watched", json={"watched": False}).json()
    assert unwatched["watched"] is False and unwatched["position_s"] == 0


def test_progress_is_per_user(admin: TestClient) -> None:
    add_and_wait(admin, "peruser0001")
    vid = video_id(admin, "peruser0001")
    admin.put(f"/api/videos/{vid}/watched", json={"watched": True})
    admin.post("/api/users", json={"username": "kim", "password": "passwort1"})

    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "kim", "password": "passwort1"})
    assert other.get(f"/api/videos/{vid}").json()["progress"] is None
    assert admin.get(f"/api/videos/{vid}").json()["progress"]["watched"] is True


def test_watched_filters(admin: TestClient) -> None:
    for yid in ("filterseen1", "filterhalf1", "filternew01"):
        add_and_wait(admin, yid)
    admin.put(f"/api/videos/{video_id(admin, 'filterseen1')}/watched", json={"watched": True})
    admin.put(f"/api/videos/{video_id(admin, 'filterhalf1')}/progress", json={"position_s": 30})

    def ids(watched: str) -> set[str]:
        items = admin.get("/api/videos", params={"watched": watched}).json()["items"]
        return {v["youtube_id"] for v in items}

    assert ids("watched") == {"filterseen1"}
    assert ids("in_progress") == {"filterhalf1"}
    assert ids("unwatched") == {"filterhalf1", "filternew01"}
    assert len(ids("all")) == 3


# --- home and channels -------------------------------------------------------------------


def test_home_feed(admin: TestClient, catalog: FakeCatalog) -> None:
    add_and_wait(admin, "homemanual1")
    add_and_wait(admin, "homemanual2")
    admin.put(f"/api/videos/{video_id(admin, 'homemanual1')}/progress", json={"position_s": 50})

    feed = admin.get("/api/home").json()
    assert [v["youtube_id"] for v in feed["continue_watching"]] == ["homemanual1"]
    assert feed["hero"]["youtube_id"] == "homemanual1"
    assert feed["from_subscriptions"] == []
    assert {v["youtube_id"] for v in feed["recently_added"]} == {"homemanual1", "homemanual2"}
    channel = feed["channels"][0]
    assert channel["name"] == "Test Channel"
    assert channel["video_count"] == 2
    assert channel["unwatched_count"] == 2


def test_channels_and_artwork(admin: TestClient, settings: Any) -> None:
    add_and_wait(admin, "artwork0001")
    channels = admin.get("/api/channels").json()
    assert len(channels) == 1
    channel_id = channels[0]["id"]

    # Channels of hand-added videos get their artwork in the background.
    wait_for(lambda: admin.get(f"/api/channels/{channel_id}").json()["has_avatar"])
    detail = admin.get(f"/api/channels/{channel_id}").json()
    assert detail["video_count"] == 1 and detail["subscription_id"] is None
    assert admin.get(f"/api/channels/{channel_id}/banner").status_code == 200
    assert admin.get("/api/channels/9999").status_code == 404


# --- search ---------------------------------------------------------------------------


def test_fts_query_building() -> None:
    assert fts_query("Raspberry Pi") == '"raspberry"* AND "pi"*'
    assert fts_query('"; DROP TABLE videos; --') == '"drop"* AND "table"* AND "videos"*'
    assert fts_query("   ") is None


def test_full_text_search(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.meta_overrides = {
        "searchtitle": {"title": "Größte Brücken der Welt", "description": "Bauwerke"},
        "searchdescr": {"title": "Ein Spaziergang", "description": "Wir laufen über eine Brücke"},
        "searchother": {"title": "Kochen mit Gemüse", "description": "Nichts hier"},
    }
    for yid in downloader.meta_overrides:
        add_and_wait(admin, yid)

    def search(q: str, **params: Any) -> list[str]:
        items = admin.get("/api/videos", params={"q": q, **params}).json()["items"]
        return [v["youtube_id"] for v in items]

    # Prefix match, umlaut-insensitive, title hits rank above description hits.
    assert search("brucke") == ["searchtitle", "searchdescr"]
    assert search("Größ") == ["searchtitle"]
    assert search("gemuse kochen") == ["searchother"]
    assert search("test channel", sort="title") == sorted(
        ["searchtitle", "searchdescr", "searchother"],
        key=lambda y: downloader.meta_overrides[y]["title"].lower(),
    )
    assert search("nichtvorhanden") == []


# --- playlists --------------------------------------------------------------------------


def test_playlists(admin: TestClient) -> None:
    for yid in ("playlist001", "playlist002", "playlist003"):
        add_and_wait(admin, yid)
    a, b, c = (video_id(admin, y) for y in ("playlist001", "playlist002", "playlist003"))

    created = admin.post("/api/playlists", json={"name": "  Abends  "}).json()
    assert created["name"] == "Abends" and created["video_count"] == 0
    pid = created["id"]
    for vid in (a, b, c, a):  # adding twice is a no-op
        admin.post(f"/api/playlists/{pid}/items", json={"video_id": vid})

    detail = admin.get(f"/api/playlists/{pid}").json()
    assert [v["id"] for v in detail["videos"]] == [a, b, c]
    assert detail["duration_s"] == 360 and len(detail["cover"]) == 3

    admin.put(f"/api/playlists/{pid}/order", json={"video_ids": [c, a]})
    assert [v["id"] for v in admin.get(f"/api/playlists/{pid}").json()["videos"]] == [c, a, b]

    membership = admin.get("/api/playlists", params={"video_id": b}).json()
    assert membership[0]["contains"] is True
    admin.delete(f"/api/playlists/{pid}/items/{b}")
    assert admin.get("/api/playlists", params={"video_id": b}).json()[0]["contains"] is False

    renamed = admin.patch(f"/api/playlists/{pid}", json={"name": "Später"}).json()
    assert renamed["name"] == "Später"
    assert admin.post("/api/playlists", json={"name": "   "}).status_code == 422

    admin.post("/api/users", json={"username": "lea", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "lea", "password": "passwort1"})
    assert other.get(f"/api/playlists/{pid}").status_code == 404
    assert other.get("/api/playlists").json() == []

    assert admin.delete(f"/api/playlists/{pid}").status_code == 204
    assert admin.get("/api/playlists").json() == []


# --- SponsorBlock -------------------------------------------------------------------------

SB_PAYLOAD = [
    {"videoID": "other", "segments": [{"segment": [1, 2], "category": "sponsor", "UUID": "x"}]},
    {
        "videoID": "sponsorvid1",
        "segments": [
            {"segment": [30, 45.5], "category": "sponsor", "UUID": "a", "actionType": "skip"},
            {"segment": [0, 5], "category": "intro", "UUID": "b", "actionType": "skip"},
            {"segment": [60, 70], "category": "selfpromo", "UUID": "c", "actionType": "poi"},
            {"segment": [80, 70], "category": "sponsor", "UUID": "d"},
        ],
    },
]


def test_parse_sponsorblock_response() -> None:
    segments = parse_response(SB_PAYLOAD, "sponsorvid1", ["sponsor", "selfpromo"])
    assert segments == [Segment("a", "sponsor", "skip", 30.0, 45.5)]
    assert parse_response({"bad": 1}, "x", ["sponsor"]) == []


def test_sponsorblock_skip_mode(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_fetch(youtube_id: str, categories: list[str], timeout: float = 10) -> list[Segment]:
        calls.append((youtube_id, categories))
        return parse_response(SB_PAYLOAD, youtube_id, categories)

    monkeypatch.setattr(sponsorblock, "fetch_segments", fake_fetch)
    settings = admin.get("/api/settings").json()
    settings["downloads"]["sponsorblock_mode"] = "skip"
    settings["downloads"]["sponsorblock_categories"] = ["sponsor", "intro"]
    assert admin.put("/api/settings", json=settings).status_code == 200

    add_and_wait(admin, "sponsorvid1")
    vid = video_id(admin, "sponsorvid1")
    assert calls == [("sponsorvid1", ["sponsor", "intro"])]  # fetched right after the download

    segments = admin.get(f"/api/videos/{vid}/segments").json()
    assert segments["mode"] == "skip" and segments["cut"] is False
    assert [(s["category"], s["start_s"]) for s in segments["segments"]] == [
        ("intro", 0.0),
        ("sponsor", 30.0),
    ]
    assert len(calls) == 1  # fresh enough, not fetched again


def test_sponsorblock_cut_uses_ytdlp_postprocessors() -> None:
    cut = YtDlpDownloader._postprocessors(
        DownloadOptions(sponsorblock_mode="cut", sponsorblock_categories=["sponsor"])
    )
    keys = [pp["key"] for pp in cut]
    assert keys.index("SponsorBlock") < keys.index("ModifyChapters") < keys.index("FFmpegMetadata")
    assert cut[keys.index("ModifyChapters")]["remove_sponsor_segments"] == ["sponsor"]
    plain = [pp["key"] for pp in YtDlpDownloader._postprocessors(DownloadOptions())]
    assert "SponsorBlock" not in plain and "ModifyChapters" not in plain


def test_is_stale() -> None:
    from datetime import UTC, datetime, timedelta

    from app.models import Video

    now = datetime(2026, 10, 2, tzinfo=UTC)
    video = Video(youtube_id="x", title="t", upload_date=date(2026, 9, 30))
    assert sponsorblock.is_stale(video, now)
    video.sponsorblock_fetched_at = now - timedelta(hours=2)
    assert not sponsorblock.is_stale(video, now)
    video.sponsorblock_fetched_at = now - timedelta(days=1)
    assert sponsorblock.is_stale(video, now)  # recent upload: refresh twice a day
    video.upload_date = date(2025, 1, 1)
    assert not sponsorblock.is_stale(video, now)
    video.sponsorblock_cut = True
    video.sponsorblock_fetched_at = None
    assert not sponsorblock.is_stale(video, now)


def test_preferences_are_merged(admin: TestClient) -> None:
    admin.put("/api/auth/me/preferences", json={"theme": "light"})
    prefs = admin.put("/api/auth/me/preferences", json={"sponsorblock_skip": False}).json()
    assert prefs["preferences"] == {"theme": "light", "sponsorblock_skip": False}
