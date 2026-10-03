"""Without internet the library keeps working; online work waits instead of failing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import __main__ as cli
from app.models import Subscription
from app.services import sponsorblock
from app.services.connectivity import Connectivity
from tests.conftest import FakeCatalog, FakeDownloader, FakeNetwork, add_and_wait, wait_for
from tests.test_subscriptions import subscribe


def _job(client: TestClient, job_id: int) -> dict[str, Any]:
    return dict(next(j for j in client.get("/api/downloads").json()["items"] if j["id"] == job_id))


def test_connectivity_probes_only_when_needed() -> None:
    answers = [False, False, True]
    changes: list[bool] = []
    net = Connectivity(probe=lambda: answers.pop(0), recheck_s=3600, on_change=changes.append)

    assert net.should_wait() is False and answers == [False, False, True]  # online: no probe
    assert net.confirm_offline() is True and changes == [False]
    assert net.offline_since is not None
    # Within recheck_s nothing is probed again.
    assert net.should_wait() is True and net.confirm_offline() is True
    assert answers == [False, True]

    net.report_success()
    assert net.online and net.offline_since is None and changes == [False, True]


def test_downloads_wait_for_the_internet(
    admin: TestClient, downloader: FakeDownloader, network: FakeNetwork
) -> None:
    network.online = False
    downloader.errors.append(Exception("ERROR: Unable to download webpage: <urlopen error>"))
    job_id = admin.post("/api/videos", json={"url": "https://youtu.be/offline0001"}).json()["id"]

    job = wait_for(lambda: (j := _job(admin, job_id))["error_message"] and j)
    assert job["status"] == "queued" and job["attempts"] == 0
    assert "Keine Internetverbindung" in job["error_message"]
    state = admin.get("/api/downloads/state").json()
    assert state["online"] is False and state["offline_since"]

    # Still offline: a manual retry does not burn attempts either.
    admin.post(f"/api/downloads/{job_id}/retry")
    assert _job(admin, job_id)["status"] == "queued"

    network.online = True
    admin.post(f"/api/downloads/{job_id}/retry")
    wait_for(lambda: _job(admin, job_id)["status"] == "completed")
    assert admin.get("/api/downloads/state").json()["online"] is True


def test_a_hiccup_is_an_ordinary_retry(
    admin: TestClient, downloader: FakeDownloader, network: FakeNetwork
) -> None:
    downloader.errors.append(ConnectionError("Connection reset by peer"))
    job_id = admin.post("/api/videos", json={"url": "https://youtu.be/hiccup00001"}).json()["id"]
    job = wait_for(lambda: (j := _job(admin, job_id))["next_attempt_at"] and j)
    assert job["attempts"] == 1 and "Connection reset" in job["error_message"]
    assert network.probes == 1


def test_subscription_checks_wait_quietly(
    admin: TestClient, catalog: FakeCatalog, network: FakeNetwork
) -> None:
    sub = subscribe(admin)
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    wait_for(lambda: admin.get(f"/api/subscriptions/{sub['id']}").json()["last_checked_at"])
    wait_for(lambda: not ctx.checker.is_checking(sub["id"]))
    network.online = False
    catalog.list_error = Exception("ERROR: Unable to download webpage: timed out")
    before = datetime.now(UTC)

    assert ctx.checker.check(sub["id"]) is None
    with ctx.sessions() as db:
        stored = db.get(Subscription, sub["id"])
        assert stored.last_check_error is None
        assert stored.next_check_at.replace(tzinfo=UTC) > before

    # While offline the next check does not even try YouTube.
    calls = len(catalog.calls)
    assert ctx.checker.check(sub["id"]) is None
    assert len(catalog.calls) == calls


def test_video_page_never_waits_for_sponsorblock_offline(
    admin: TestClient, network: FakeNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fetch(youtube_id: str, categories: list[str], timeout: float = 10) -> list[Any]:
        calls.append(youtube_id)
        raise OSError("network is unreachable")

    monkeypatch.setattr(sponsorblock, "fetch_segments", fetch)
    settings = admin.get("/api/settings").json()
    settings["downloads"]["sponsorblock_mode"] = "skip"
    assert admin.put("/api/settings", json=settings).status_code == 200
    add_and_wait(admin, "sponsoroff1")
    video_id = admin.get("/api/videos").json()["items"][0]["id"]
    assert calls == ["sponsoroff1"]  # tried right after the download

    calls.clear()
    sponsorblock._failures.clear()
    network.online = False
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    ctx.connectivity.confirm_offline()
    assert admin.get(f"/api/videos/{video_id}/segments").json()["segments"] == []
    assert calls == []

    # Online but SponsorBlock fails: one try, then a pause instead of a try per page view.
    network.online = True
    ctx.connectivity.report_success()
    admin.get(f"/api/videos/{video_id}/segments")
    admin.get(f"/api/videos/{video_id}/segments")
    assert calls == ["sponsoroff1"]


def test_startup_update_skips_without_internet(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], settings: Any
) -> None:
    from app.services import ytdlp_updater

    monkeypatch.setattr(ytdlp_updater, "pypi_reachable", lambda: False)

    def no_pip(_dir: Any) -> None:
        raise AssertionError("pip must not run offline")

    monkeypatch.setattr(ytdlp_updater, "update_ytdlp", no_pip)
    settings.ytdlp_auto_update = True
    cli.update_ytdlp(settings, only_if_enabled=True)
    assert "Kein Internet" in capsys.readouterr().out


def test_ui_loads_nothing_from_outside(admin: TestClient) -> None:
    policy = admin.get("/api/health").headers["content-security-policy"]
    assert "default-src 'self'" in policy and "script-src 'self';" in policy
