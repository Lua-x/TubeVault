from __future__ import annotations

import json
from collections import namedtuple
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.notifications import Message, NotificationConfig, NotifyError, build_request
from app.workers import scheduler as scheduler_module
from tests.conftest import HEADERS, FakeCatalog, FakeDownloader, FakeSender, add_and_wait, wait_for
from tests.test_subscriptions import subscribe

WEBHOOK = {"service": "webhook", "url": "http://nas.local:8080/hook"}


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _flush(client: TestClient) -> None:
    _ctx(client).notifier.flush(force=True)


def test_requests_per_service() -> None:
    message = Message("video_downloaded", "Neues Video", "Bergsee in 4K\nStille Natur", {"a": 1})

    ntfy = build_request(
        NotificationConfig(service="ntfy", url="https://ntfy.example.org/tubevault", token="tk"),
        message,
    )
    assert ntfy.full_url == "https://ntfy.example.org/"
    assert ntfy.get_header("Authorization") == "Bearer tk"
    body = json.loads(ntfy.data)  # type: ignore[arg-type]
    assert body["topic"] == "tubevault" and body["title"] == "Neues Video"

    gotify = build_request(
        NotificationConfig(service="gotify", url="http://gotify.local/", token="app"), message
    )
    assert gotify.full_url == "http://gotify.local/message"
    assert gotify.get_header("X-gotify-key") == "app"

    hook = build_request(NotificationConfig(**WEBHOOK), message)
    payload = json.loads(hook.data)  # type: ignore[arg-type]
    assert payload["event"] == "video_downloaded" and payload["data"] == {"a": 1}

    with pytest.raises(NotifyError, match="Token"):
        build_request(NotificationConfig(service="gotify", url="http://g.local"), message)
    with pytest.raises(ValueError, match="http"):
        NotificationConfig(service="webhook", url="ftp://x")


def test_settings_keep_the_token_secret(admin: TestClient) -> None:
    assert admin.get("/api/admin/notifications").json()["service"] == "off"
    saved = admin.put(
        "/api/admin/notifications",
        json={"service": "gotify", "url": "http://g.local", "token": "s3"},
    ).json()
    assert saved["has_token"] is True and "token" not in saved
    # Saving without a token keeps it; "" removes it.
    kept = admin.put(
        "/api/admin/notifications", json={"service": "gotify", "url": "http://g.local"}
    )
    assert kept.json()["has_token"] is True
    assert "s3" not in admin.get("/api/settings").text
    bad = admin.put("/api/admin/notifications", json={"service": "webhook", "url": "nas.local"})
    assert bad.status_code == 422 and "http" in bad.json()["detail"]

    admin.post("/api/users", json={"username": "gast", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "gast", "password": "passwort1"})
    assert other.get("/api/admin/notifications").status_code == 403


def test_test_message(admin: TestClient, sender: FakeSender) -> None:
    assert admin.post("/api/admin/notifications/test", json={"service": "off"}).status_code == 400
    assert admin.post("/api/admin/notifications/test", json=WEBHOOK).status_code == 200
    assert sender.messages[-1].event == "test"
    sender.error = NotifyError("Nicht erreichbar: Connection refused")
    failed = admin.post("/api/admin/notifications/test", json=WEBHOOK)
    assert failed.status_code == 400 and "Connection refused" in failed.json()["detail"]


def test_downloads_are_collected_into_one_message(admin: TestClient, sender: FakeSender) -> None:
    add_and_wait(admin, "notify00001")
    _flush(admin)
    assert sender.messages == []  # off by default

    admin.put("/api/admin/notifications", json=WEBHOOK)
    add_and_wait(admin, "notify00002")
    add_and_wait(admin, "notify00003")
    _flush(admin)
    assert len(sender.messages) == 1
    summary = sender.messages[0]
    assert summary.title == "2 neue Videos" and "Video notify00002: Test" in summary.body

    add_and_wait(admin, "notify00004")
    _flush(admin)
    assert sender.messages[-1].title == "Neues Video"


def test_failures_and_events_can_be_switched_off(
    admin: TestClient, sender: FakeSender, downloader: FakeDownloader
) -> None:
    admin.put(
        "/api/admin/notifications",
        json={**WEBHOOK, "events": {"video_downloaded": False, "download_failed": True}},
    )
    add_and_wait(admin, "notify00010")
    downloader.errors.append(Exception("ERROR: [youtube] notify00011: Private video"))
    add_and_wait(admin, "notify00011")
    _flush(admin)
    assert [m.title for m in sender.messages] == ["Download fehlgeschlagen"]
    assert "Private video" in sender.messages[0].body


def test_subscription_errors_once_per_problem(
    admin: TestClient, sender: FakeSender, catalog: FakeCatalog
) -> None:
    admin.put("/api/admin/notifications", json=WEBHOOK)
    sub = subscribe(admin)
    ctx = _ctx(admin)
    wait_for(lambda: admin.get(f"/api/subscriptions/{sub['id']}").json()["last_checked_at"])
    wait_for(lambda: not ctx.checker.is_checking(sub["id"]))
    catalog.list_error = Exception("ERROR: This channel does not exist")
    ctx.checker.check(sub["id"])
    ctx.checker.check(sub["id"])
    _flush(admin)
    assert [m.title for m in sender.messages] == ["Abo-Prüfung fehlgeschlagen"]


def test_low_disk_space_warns_once(
    admin: TestClient, sender: FakeSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin.put("/api/admin/notifications", json=WEBHOOK)
    usage = namedtuple("usage", "total used free")
    gb = 1024**3
    monkeypatch.setattr(
        scheduler_module.shutil, "disk_usage", lambda _p: usage(500 * gb, 498 * gb, 2 * gb)
    )
    scheduler = _ctx(admin).scheduler
    scheduler.cleanup()
    scheduler.cleanup()
    _flush(admin)
    assert [m.title for m in sender.messages] == ["Speicherplatz wird knapp"]
    assert "2.0 GB" in sender.messages[0].body
