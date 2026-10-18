"""Thumbnails and channel art come from small copies in /config, so browsing the library
leaves the disks with the videos asleep – like Jellyfin's image cache."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.models import Channel, Video
from app.services import upgrades as upgrades_module
from app.services.image_cache import ImageWarmer
from app.services.upgrades import QualityUpgrades
from tests.conftest import FakeDownloader, add_and_wait


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _picture(path: Path, size: tuple[int, int] = (1280, 720)) -> None:
    """A real JPEG where the test downloader leaves a placeholder."""
    Image.new("RGB", size, (200, 40, 40)).save(path, "JPEG")


def _video_with_thumbnail(client: TestClient, youtube_id: str) -> tuple[int, Path]:
    add_and_wait(client, youtube_id)
    ctx = _ctx(client)
    with ctx.sessions() as db:
        video = db.query(Video).filter_by(youtube_id=youtube_id).one()
        original = ctx.settings.media_dir / video.thumbnail_path
        _picture(original)
        return video.id, original


def _width(body: bytes) -> int:
    with Image.open(io.BytesIO(body)) as image:
        return image.width


def test_thumbnails_come_from_config(admin: TestClient) -> None:
    video_id, original = _video_with_thumbnail(admin, "cachethumb1")
    small = admin.get(f"/api/videos/{video_id}/thumbnail?size=small&v=1")
    assert small.status_code == 200
    assert small.headers["content-type"] == "image/jpeg"
    assert "immutable" in small.headers["cache-control"]
    assert _width(small.content) == 640
    large = admin.get(f"/api/videos/{video_id}/thumbnail")  # podcast apps & co: large
    assert _width(large.content) == 1280

    copies = sorted(p.name for p in _ctx(admin).settings.image_cache_dir.iterdir())
    assert [name.split("-")[2] for name in copies] == ["large", "small"]

    # The disk is asleep (here: the original is out of reach) – the pictures still come.
    original.rename(original.with_suffix(".away"))
    assert admin.get(f"/api/videos/{video_id}/thumbnail?size=small").status_code == 200
    assert admin.get(f"/api/videos/{video_id}/thumbnail?size=large").status_code == 200


def test_pictures_that_cannot_be_shrunk_are_served_as_they_are(admin: TestClient) -> None:
    add_and_wait(admin, "cachethumb2")  # the test downloader's thumbnail is no real JPEG
    video = admin.get("/api/videos", params={"q": "cachethumb2"}).json()["items"][0]
    response = admin.get(f"/api/videos/{video['id']}/thumbnail?size=small")
    assert response.status_code == 200
    assert response.content.endswith(b"fakejpeg")
    assert admin.get("/api/videos/99999/thumbnail").status_code == 404


def test_channel_art_comes_from_config(admin: TestClient) -> None:
    video_id, _ = _video_with_thumbnail(admin, "cachethumb3")
    ctx = _ctx(admin)
    with ctx.sessions() as db:
        channel = db.get(Video, video_id).channel
        avatar = ctx.settings.media_dir / "avatar.jpg"
        _picture(avatar, (900, 900))
        channel.avatar_path = "avatar.jpg"
        db.commit()
        channel_id = channel.id
    response = admin.get(f"/api/channels/{channel_id}/avatar?v=1")
    assert response.status_code == 200
    assert _width(response.content) == 256
    avatar.unlink()
    assert admin.get(f"/api/channels/{channel_id}/avatar?v=1").status_code == 200


def test_the_warmer_fills_and_tidies_the_cache(admin: TestClient) -> None:
    ctx = _ctx(admin)
    first, _ = _video_with_thumbnail(admin, "cachewarm01")
    second, _ = _video_with_thumbnail(admin, "cachewarm02")
    with ctx.sessions() as db:  # an older download: only the small copy ahead of time
        db.get(Video, second).downloaded_at = datetime.now(UTC) - timedelta(days=30)
        db.commit()
    warmer = ImageWarmer(ctx.sessions, ctx.images)
    assert warmer.run_round() == 3  # small + large for the new one, small for the old one
    names = {p.name.rsplit("-", 1)[0] for p in ctx.settings.image_cache_dir.iterdir()}
    assert names == {f"video-{first}-small", f"video-{first}-large", f"video-{second}-small"}
    assert warmer.run_round() == 0  # nothing missing: nothing read from the disks

    # Started watching: it can be the big picture on the start page, so the large copy too.
    admin.put(f"/api/videos/{second}/progress", json={"position_s": 30, "duration_s": 600})
    assert warmer.run_round() == 1

    # A better version arrives: new copies, the old ones go.
    with ctx.sessions() as db:
        db.get(Video, first).downloaded_at = datetime.now(UTC)
        db.commit()
    assert warmer.run_round() == 2
    assert len(list(ctx.settings.image_cache_dir.iterdir())) == 4
    # The video is deleted: its copies go too.
    admin.delete(f"/api/videos/{first}")
    warmer.run_round()
    names = {p.name.rsplit("-", 1)[0] for p in ctx.settings.image_cache_dir.iterdir()}
    assert names == {f"video-{second}-small", f"video-{second}-large"}
    with ctx.sessions() as db:
        assert db.query(Channel).count() == 1


def test_quality_check_leaves_the_disk_alone_without_an_upgrade(
    admin: TestClient, downloader: FakeDownloader, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloader.height = 720
    add_and_wait(admin, "cachecheck1")
    ctx = _ctx(admin)
    with ctx.sessions() as db:
        video = db.query(Video).filter_by(youtube_id="cachecheck1").one()
        video.downloaded_at = datetime.now(UTC) - timedelta(hours=3)
        db.commit()
    looked: list[int] = []
    real = upgrades_module.video_file_exists
    monkeypatch.setattr(
        upgrades_module,
        "video_file_exists",
        lambda media_dir, v: looked.append(v.id) or real(media_dir, v),
    )
    checks = QualityUpgrades(ctx.sessions, ctx.settings.media_dir, downloader)
    downloader.meta_overrides["cachecheck1"] = {"raw": {"formats": [{"height": 720}]}}
    assert checks.run_round() == []
    assert looked == []  # YouTube has nothing better: the file wasn't even looked at
