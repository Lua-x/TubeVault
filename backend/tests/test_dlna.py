"""DLNA: off by default, only for the home network, and only what the chosen account sees."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from app.services import dlna
from tests.conftest import VIDEO_BYTES, FakeDownloader, add_and_wait
from tests.test_access import _login

LAN = ("192.168.1.20", 50000)
DIDL = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}"
DC = "{http://purl.org/dc/elements/1.1/}"


class FakeSsdp:
    """Stands in for the multicast socket, so tests never touch port 1900."""

    started: ClassVar[list[FakeSsdp]] = []

    def __init__(self, udn: str, location_for: Callable[[str], str]) -> None:
        self.udn = udn
        self.location_for = location_for
        self.error: str | None = None
        self.stopped = False

    def start(self) -> bool:
        FakeSsdp.started.append(self)
        return True

    def stop(self) -> None:
        self.stopped = True


def _configure(admin: TestClient, **dlna_options: Any) -> None:
    current = admin.get("/api/settings").json()
    current["dlna"] = {**current["dlna"], **dlna_options}
    response = admin.put("/api/settings", json=current)
    assert response.status_code == 200, response.text


@pytest.fixture
def tv(admin: TestClient) -> TestClient:
    FakeSsdp.started.clear()
    admin.app.state.ctx.dlna._factory = FakeSsdp  # type: ignore[attr-defined]
    return TestClient(admin.app, client=LAN)


@pytest.fixture
def library(admin: TestClient, downloader: FakeDownloader) -> dict[str, int]:
    downloader.meta_overrides["dlnakids001"] = {"channel_id": "UCkids", "channel_name": "Kinder"}
    for youtube_id in ("dlnakids001", "dlnagrown01", "dlnagrown02"):
        add_and_wait(admin, youtube_id)
    channels = {c["name"]: c["id"] for c in admin.get("/api/channels").json()}
    videos = {v["youtube_id"]: v["id"] for v in admin.get("/api/videos").json()["items"]}
    return {
        "kids_channel": channels["Kinder"],
        "other_channel": channels["Test Channel"],
        "kids_video": videos["dlnakids001"],
        "other_video": videos["dlnagrown01"],
    }


def _soap(action: str, service: str = "ContentDirectory", **args: str | int) -> str:
    inner = "".join(f"<{key}>{value}</{key}>" for key, value in args.items())
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        f'<u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">{inner}</u:{action}>'
        "</s:Body></s:Envelope>"
    )


def _browse(
    tv: TestClient,
    object_id: str,
    flag: str = "BrowseDirectChildren",
    start: int = 0,
    count: int = 0,
) -> tuple[ET.Element, int]:
    response = tv.post(
        "/dlna/control/ContentDirectory",
        content=_soap(
            "Browse",
            ObjectID=object_id,
            BrowseFlag=flag,
            Filter="*",
            StartingIndex=start,
            RequestedCount=count,
            SortCriteria="",
        ),
        headers={"SOAPACTION": f'"{dlna.CONTENT_DIRECTORY}#Browse"'},
    )
    assert response.status_code == 200, response.text
    values = {el.tag: el.text or "" for el in ET.fromstring(response.content).iter()}
    didl = ET.fromstring(values["Result"])
    assert int(values["NumberReturned"]) == len(didl)
    return didl, int(values["TotalMatches"])


def _titles(didl: ET.Element) -> list[str]:
    return [entry.findtext(f"{DC}title") or "" for entry in didl]


def test_off_by_default_and_only_for_the_home_network(admin: TestClient, tv: TestClient) -> None:
    assert tv.get("/dlna/description.xml").status_code == 404
    assert admin.get("/api/settings/dlna").json()["running"] is False

    _configure(admin, enabled=True, name="Wohnzimmer")
    status = admin.get("/api/settings/dlna").json()
    assert status["running"] is True and status["error"] is None
    assert status["description_url"].endswith(":8823/dlna/description.xml")
    assert len(FakeSsdp.started) == 1 and FakeSsdp.started[0].udn.startswith("uuid:")

    response = tv.get("/dlna/description.xml")
    assert response.status_code == 200
    device = ET.fromstring(response.content)
    ns = "{urn:schemas-upnp-org:device-1-0}"
    assert device.findtext(f"{ns}device/{ns}friendlyName") == "Wohnzimmer"
    assert device.findtext(f"{ns}device/{ns}UDN") == FakeSsdp.started[0].udn
    assert tv.get("/dlna/ContentDirectory.xml").status_code == 200

    # Not from the internet, not through a reverse proxy, not without an address.
    outside = TestClient(admin.app, client=("8.8.8.8", 40000))
    assert outside.get("/dlna/description.xml").status_code == 403
    proxied = tv.get("/dlna/description.xml", headers={"X-Forwarded-For": "8.8.8.8"})
    assert proxied.status_code == 403
    assert TestClient(admin.app).get("/dlna/description.xml").status_code == 403

    # The identity survives a restart of the announcements.
    _configure(admin, enabled=False)
    assert FakeSsdp.started[0].stopped
    assert tv.get("/dlna/description.xml").status_code == 404
    _configure(admin, enabled=True)
    assert FakeSsdp.started[1].udn == FakeSsdp.started[0].udn


def test_browse_folders_and_play(
    admin: TestClient, tv: TestClient, library: dict[str, int]
) -> None:
    _configure(admin, enabled=True)
    root, total = _browse(tv, "0")
    assert _titles(root) == ["Kanäle", "Zuletzt hinzugefügt"] and total == 2

    channels, total = _browse(tv, "channels")
    assert _titles(channels) == ["Kinder", "Test Channel"] and total == 2
    assert channels[1].get("childCount") == "2"

    videos, total = _browse(tv, f"channel-{library['other_channel']}")
    assert total == 2
    item = videos[0]
    assert item.tag == f"{DIDL}item"
    res = item.find(f"{DIDL}res")
    assert res is not None and res.text
    assert res.get("protocolInfo", "").startswith("http-get:*:video/mp4:DLNA.ORG_OP=01")
    assert res.get("duration") == "0:02:00.000"

    media_path = res.text.split("192.168.1.20", 1)[-1].split("testserver", 1)[-1]
    response = tv.get(media_path, headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and response.content == VIDEO_BYTES[:10]
    assert response.headers["transfermode.dlna.org"] == "Streaming"
    assert tv.head(media_path).status_code == 200
    art = item.findtext("{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI") or ""
    assert tv.get(art.split("testserver", 1)[-1]).status_code == 200

    # Paging and the details of one entry.
    page, total = _browse(tv, "recent", start=1, count=1)
    assert len(page) == 1 and total == 3
    meta, _ = _browse(tv, item.get("id", ""), flag="BrowseMetadata")
    assert _titles(meta) == [item.findtext(f"{DC}title")]

    missing = tv.post(
        "/dlna/control/ContentDirectory",
        content=_soap("Browse", ObjectID="channel-999", BrowseFlag="BrowseDirectChildren"),
    )
    assert missing.status_code == 500 and b"<errorCode>701</errorCode>" in missing.content


def test_the_chosen_profile_decides(
    admin: TestClient, tv: TestClient, library: dict[str, int]
) -> None:
    kid = _login(admin, "kind", channel_access="selected", channel_ids=[library["kids_channel"]])
    later = kid.get("/api/playlists/watch-later").json()["id"]
    added = kid.post(f"/api/playlists/{later}/items", json={"video_id": library["kids_video"]})
    assert added.status_code == 201
    kid.post("/api/playlists", json={"name": "Leer"})
    kid_id = kid.get("/api/auth/me").json()["id"]
    _configure(admin, enabled=True, user_id=kid_id)

    root, _ = _browse(tv, "0")
    assert _titles(root) == ["Kanäle", "Zuletzt hinzugefügt", "Playlists"]
    channels, _ = _browse(tv, "channels")
    assert _titles(channels) == ["Kinder"]
    recent, total = _browse(tv, "recent")
    assert total == 1 and len(recent) == 1
    playlists, _ = _browse(tv, "playlists")
    assert _titles(playlists) == ["Später ansehen"]

    hidden = library["other_video"]
    assert tv.get(f"/dlna/media/{hidden}.mp4").status_code == 404
    assert tv.get(f"/dlna/thumbs/{hidden}.jpg").status_code == 404
    blocked = tv.post(
        "/dlna/control/ContentDirectory",
        content=_soap("Browse", ObjectID=f"channel-{library['other_channel']}"),
    )
    assert blocked.status_code == 500
    assert tv.get(f"/dlna/media/{library['kids_video']}.mp4").status_code == 200

    # The profile is deleted: nothing is shown instead of everything.
    assert admin.delete(f"/api/users/{kid_id}").status_code == 204
    assert tv.get("/dlna/description.xml").status_code == 404


def test_other_upnp_calls(admin: TestClient, tv: TestClient) -> None:
    _configure(admin, enabled=True)
    subscribed = tv.request("SUBSCRIBE", "/dlna/event/ContentDirectory")
    assert subscribed.status_code == 200 and subscribed.headers["SID"].startswith("uuid:")
    protocols = tv.post(
        "/dlna/control/ConnectionManager", content=_soap("GetProtocolInfo", "ConnectionManager")
    )
    assert protocols.status_code == 200 and b"http-get:*:video/mp4:*" in protocols.content
    update = tv.post("/dlna/control/ContentDirectory", content=_soap("GetSystemUpdateID"))
    assert update.status_code == 200 and b"<Id>" in update.content
    unknown = tv.post("/dlna/control/ContentDirectory", content=_soap("X_GetFeatureList"))
    assert unknown.status_code == 500 and b"<errorCode>401</errorCode>" in unknown.content
    garbage = tv.post("/dlna/control/ContentDirectory", content=b"<nope")
    assert garbage.status_code == 500


def test_ssdp_answers() -> None:
    udn = "uuid:1234"
    location = "http://192.168.1.5:8096/dlna/description.xml"
    search = (
        "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\nMX: 2\r\nST: {}\r\n\r\n'
    )
    every = dlna.search_responses(search.format("ssdp:all").encode(), udn, location)
    assert len(every) == 5 and all(f"LOCATION: {location}".encode() in a for a in every)
    servers = dlna.search_responses(search.format(dlna.DEVICE_TYPE).encode(), udn, location)
    assert len(servers) == 1 and b"USN: uuid:1234::urn:schemas-upnp-org" in servers[0]
    printer = "urn:schemas-upnp-org:device:Printer:1"
    assert dlna.search_responses(search.format(printer).encode(), udn, location) == []
    assert dlna.search_responses(b"NOTIFY * HTTP/1.1\r\n\r\n", udn, location) == []

    alive = dlna.notify_messages(udn, location, alive=True)
    byebye = dlna.notify_messages(udn, location, alive=False)
    assert all(b"NTS: ssdp:alive" in m and b"LOCATION:" in m for m in alive)
    assert all(b"NTS: ssdp:byebye" in m and b"LOCATION:" not in m for m in byebye)

    assert dlna.is_home_network("192.168.0.4") and dlna.is_home_network("10.1.2.3")
    assert dlna.is_home_network("fe80::1") and not dlna.is_home_network("8.8.8.8")
    assert not dlna.is_home_network("testclient") and not dlna.is_home_network(None)


def test_didl_escapes_titles() -> None:
    text = dlna.didl(
        [
            dlna.Container("c", "0", "Tom & Jerry <3", 1),
            dlna.Item("c/v1", "c", 'Ein "Video"', "http://x/dlna/media/1.mp4", "video/mp4"),
        ]
    )
    parsed = ET.fromstring(text)
    assert _titles(parsed) == ["Tom & Jerry <3", 'Ein "Video"']
