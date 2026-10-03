from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import SubscriptionKind
from app.services.app_settings import DownloadOptions
from app.services.catalog import Entry, Listing, SourceInfo, channel_url, playlist_url
from app.services.connectivity import Connectivity
from app.services.downloader import (
    DownloadCancelledError,
    DownloadProgress,
    DownloadResult,
    SubtitleFile,
    VideoMetadata,
)
from app.services.notifications import Message, NotificationConfig

HEADERS = {"X-Requested-With": "TubeVault"}
VIDEO_BYTES = bytes(range(256)) * 40  # 10 KiB of predictable content


class FakeDownloader:
    """Writes small files instead of talking to YouTube."""

    def __init__(self) -> None:
        self.errors: list[Exception] = []
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.downloads = 0
        # Per video ID: fields to override in the metadata (is_short, upload_date, …).
        self.meta_overrides: dict[str, dict[str, Any]] = {}
        self.height = 1080  # resolution of the "downloaded" file

    def fetch_metadata(self, url: str) -> VideoMetadata:
        youtube_id = url.rsplit("=", 1)[-1]
        meta = VideoMetadata(
            youtube_id=youtube_id,
            title=f"Video {youtube_id}: Test",
            webpage_url=url,
            description="Eine Beschreibung",
            channel_id="UCtest",
            channel_name="Test Channel",
            channel_handle="@test",
            channel_url="https://www.youtube.com/@test",
            upload_date=date(2024, 5, 1),
            duration_s=120,
            chapters=[
                {"start": 0.0, "end": 60.0, "title": "Intro"},
                {"start": 60.0, "end": 120.0, "title": "Hauptteil"},
            ],
        )
        for key, value in self.meta_overrides.get(youtube_id, {}).items():
            setattr(meta, key, value)
        return meta

    def download(
        self,
        meta: VideoMetadata,
        *,
        media_dir: Path,
        relative_base: Path,
        temp_dir: Path,
        options: DownloadOptions,
        on_progress: Callable[[DownloadProgress], None],
        is_cancelled: Callable[[], bool],
    ) -> DownloadResult:
        self.started.set()
        if self.errors:
            raise self.errors.pop(0)
        on_progress(DownloadProgress(stage="downloading", progress=0.5, downloaded_bytes=5))
        if self.gate is not None:
            while not self.gate.wait(0.02):
                if is_cancelled():
                    raise DownloadCancelledError
        self.downloads += 1
        target_dir = media_dir / relative_base.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        video = target_dir / f"{relative_base.name}.{options.container}"
        video.write_bytes(VIDEO_BYTES)
        thumb = target_dir / f"{relative_base.name}-thumb.jpg"
        thumb.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        sub = target_dir / f"{relative_base.name}.de.vtt"
        sub.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHallo\n", encoding="utf-8")
        return DownloadResult(
            file_path=video,
            thumbnail_path=thumb,
            subtitles=[SubtitleFile(lang="de", is_auto=False, path=sub)],
            width=self.height * 16 // 9,
            height=self.height,
            vcodec="avc1.640028",
            acodec="mp4a.40.2",
        )


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


class FakeCatalog:
    """Channel "Test Channel" (UCtest…) and a playlist, with entries the test controls."""

    CHANNEL_ID = "UCtest_channel_0000000001"

    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.error: Exception | None = None
        self.list_error: Exception | None = None
        self.calls: list[tuple[str, tuple[str, ...], int | None]] = []

    def source(self, kind: SubscriptionKind, url: str) -> SourceInfo:
        if kind is SubscriptionKind.PLAYLIST:
            return SourceInfo(
                kind=kind,
                youtube_id="PLtestplaylist01",
                title="Test Playlist",
                url=playlist_url("PLtestplaylist01"),
                channel_id=self.CHANNEL_ID,
                channel_name="Test Channel",
            )
        return SourceInfo(
            kind=kind,
            youtube_id=self.CHANNEL_ID,
            title="Test Channel",
            url=channel_url(self.CHANNEL_ID),
            channel_id=self.CHANNEL_ID,
            channel_name="Test Channel",
            channel_handle="@test",
            channel_url=channel_url(self.CHANNEL_ID),
            avatar_url="https://example.invalid/avatar",
            banner_url="https://example.invalid/banner",
        )

    def resolve(self, kind: SubscriptionKind, url: str) -> SourceInfo:
        if self.error:
            raise self.error
        return self.source(kind, url)

    def list_entries(
        self, kind: SubscriptionKind, url: str, *, tabs: list[str], limit: int | None
    ) -> Listing:
        self.calls.append((url, tuple(tabs), limit))
        if self.error or self.list_error:
            raise self.error or self.list_error  # type: ignore[misc]
        entries = [e for e in self.entries if not e.is_short or "shorts" in tabs]
        return Listing(self.source(kind, url), entries[:limit] if limit else entries)

    def fetch_image(self, url: str) -> bytes | None:
        return JPEG


def wait_for(predicate: Callable[[], Any], timeout: float = 5.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("Bedingung wurde nicht rechtzeitig erfüllt")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        config_dir=tmp_path / "config",
        media_dir=tmp_path / "media",
        static_dir=tmp_path / "static",
        admin_user=None,
        admin_password=None,
    )


@pytest.fixture
def downloader() -> FakeDownloader:
    return FakeDownloader()


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


class FakeNetwork:
    """Stands in for the connectivity probe, so tests never contact YouTube."""

    def __init__(self) -> None:
        self.online = True
        self.probes = 0

    def probe(self) -> bool:
        self.probes += 1
        return self.online


@pytest.fixture
def network() -> FakeNetwork:
    return FakeNetwork()


class FakeFeeds:
    """RSS feeds by URL; tests put video IDs in, nothing goes to YouTube."""

    def __init__(self) -> None:
        self.ids: dict[str, list[str]] = {}
        self.calls: list[str] = []

    def fetch(self, url: str) -> list[str]:
        self.calls.append(url)
        return self.ids.get(url, [])


@pytest.fixture
def feeds() -> FakeFeeds:
    return FakeFeeds()


class FakeSender:
    """Records notifications instead of sending them; can be told to fail."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.error: Exception | None = None

    def send(self, config: NotificationConfig, message: Message) -> None:
        if self.error:
            raise self.error
        self.messages.append(message)


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def client(
    settings: Settings,
    downloader: FakeDownloader,
    catalog: FakeCatalog,
    network: FakeNetwork,
    feeds: FakeFeeds,
    sender: FakeSender,
) -> Iterator[TestClient]:
    connectivity = Connectivity(probe=network.probe, recheck_s=0)
    app = create_app(
        settings,
        downloader,
        catalog,
        configure_logging=False,
        connectivity=connectivity,
        feeds=feeds.fetch,
        notification_sender=sender.send,
    )
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


@pytest.fixture
def admin(client: TestClient) -> TestClient:
    response = client.post("/api/auth/setup", json={"username": "admin", "password": "geheim123"})
    assert response.status_code == 201, response.text
    return client


def job_status(client: TestClient, job_id: int) -> str:
    jobs = client.get("/api/downloads").json()["items"]
    return str(next(j for j in jobs if j["id"] == job_id)["status"])


def add_and_wait(client: TestClient, youtube_id: str = "dQw4w9WgXcQ") -> dict[str, Any]:
    response = client.post("/api/videos", json={"url": f"https://youtu.be/{youtube_id}"})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    def done() -> dict[str, Any] | None:
        jobs = client.get("/api/downloads").json()["items"]
        job = next(j for j in jobs if j["id"] == job_id)
        return job if job["status"] in ("completed", "failed", "cancelled") else None

    job: dict[str, Any] = wait_for(done)
    return job
