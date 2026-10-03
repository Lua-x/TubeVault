from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from fastapi.testclient import TestClient

from app.services.podcasts import ITUNES
from tests.conftest import HEADERS, FakeDownloader, add_and_wait
from tests.test_playback import _library_video, needs_ffmpeg


def _enable(client: TestClient) -> str:
    access = client.post("/api/podcasts/token").json()
    assert access["enabled"] is True
    return str(access["base_url"])


def _path(url: str) -> str:
    return url.split("testserver", 1)[1]


def _channel_id(admin: TestClient) -> int:
    return int(admin.get("/api/channels").json()[0]["id"])


def test_feeds_need_a_token(admin: TestClient) -> None:
    add_and_wait(admin, "podcast0001")
    assert admin.get("/api/podcasts").json() == {"enabled": False, "base_url": None}
    channel = _channel_id(admin)
    assert (
        TestClient(admin.app).get(f"/api/podcast/{'x' * 43}/channels/{channel}.xml").status_code
        == 404
    )

    base = _enable(admin)
    assert "/api/podcast/" in base
    anonymous = TestClient(admin.app)  # podcast apps don't sign in
    response = anonymous.get(_path(f"{base}/channels/{channel}.xml"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")

    rss = ET.fromstring(response.content)
    channel_el = rss.find("channel")
    assert channel_el is not None
    assert channel_el.findtext("title") == "Test Channel"
    assert channel_el.findtext(f"{{{ITUNES}}}block") == "Yes"
    items = channel_el.findall("item")
    assert len(items) == 1
    enclosure = items[0].find("enclosure")
    assert enclosure is not None and enclosure.get("type") == "audio/mp4"
    assert enclosure.get("url", "").startswith(base) and enclosure.get("url", "").endswith(".m4a")
    assert int(enclosure.get("length", "0")) > 0
    assert items[0].findtext("guid") == "podcast0001"
    assert items[0].findtext(f"{{{ITUNES}}}duration") == "120"

    image = items[0].find(f"{{{ITUNES}}}image")
    assert image is not None
    assert anonymous.get(_path(image.get("href", ""))).status_code == 200

    # A new address ends the old one; switching off ends both.
    new_base = _enable(admin)
    assert new_base != base
    assert anonymous.get(_path(f"{base}/channels/{channel}.xml")).status_code == 404
    assert anonymous.get(_path(f"{new_base}/channels/{channel}.xml")).status_code == 200
    assert admin.delete("/api/podcasts/token").status_code == 204
    assert anonymous.get(_path(f"{new_base}/channels/{channel}.xml")).status_code == 404


def test_playlist_feeds_are_private(admin: TestClient) -> None:
    add_and_wait(admin, "podcast0002")
    vid = admin.get("/api/videos").json()["items"][0]["id"]
    later = admin.get("/api/playlists/watch-later").json()["id"]
    admin.post(f"/api/playlists/{later}/items", json={"video_id": vid})
    base = _enable(admin)
    anonymous = TestClient(admin.app)
    rss = ET.fromstring(anonymous.get(_path(f"{base}/playlists/{later}.xml")).content)
    assert rss.findtext("channel/title") == "Später ansehen"
    assert len(rss.findall("channel/item")) == 1

    admin.post("/api/users", json={"username": "hoerer", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "hoerer", "password": "passwort1"})
    other_base = _enable(other)
    # Someone else's playlist stays closed, even with a valid token.
    assert anonymous.get(_path(f"{other_base}/playlists/{later}.xml")).status_code == 404


def test_kids_profile_feeds(admin: TestClient, downloader: FakeDownloader) -> None:
    downloader.meta_overrides["kidscast001"] = {"channel_id": "UCkids", "channel_name": "Kinder"}
    add_and_wait(admin, "kidscast001")
    add_and_wait(admin, "growncast01")
    channels: dict[str, Any] = {c["name"]: c["id"] for c in admin.get("/api/channels").json()}
    admin.post(
        "/api/users",
        json={
            "username": "kind",
            "password": "passwort1",
            "channel_access": "selected",
            "channel_ids": [channels["Kinder"]],
        },
    )
    kid = TestClient(admin.app, headers=HEADERS)
    kid.post("/api/auth/login", json={"username": "kind", "password": "passwort1"})
    base = _enable(kid)
    anonymous = TestClient(admin.app)
    assert anonymous.get(_path(f"{base}/channels/{channels['Kinder']}.xml")).status_code == 200
    assert (
        anonymous.get(_path(f"{base}/channels/{channels['Test Channel']}.xml")).status_code == 404
    )


@needs_ffmpeg
def test_episode_audio(admin: TestClient) -> None:
    vid = _library_video(admin, "castaudio01")
    base = _enable(admin)
    response = TestClient(admin.app).get(_path(f"{base}/audio/{vid}.m4a"))
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mp4"
    assert len(response.content) > 1000
