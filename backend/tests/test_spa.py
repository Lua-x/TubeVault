from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import HEADERS, FakeDownloader

INDEX = "<!doctype html><html><head><title>TubeVault</title></head><body></body></html>"


def _client(settings: Settings, downloader: FakeDownloader, base_path: str) -> TestClient:
    settings.static_dir.mkdir(parents=True)
    (settings.static_dir / "index.html").write_text(INDEX)
    (settings.static_dir / "assets").mkdir()
    (settings.static_dir / "assets" / "app-123.js").write_text("console.log(1)")
    (settings.static_dir / "favicon.svg").write_text("<svg/>")
    settings.base_path = base_path
    return TestClient(create_app(settings, downloader, configure_logging=False), headers=HEADERS)


def test_spa_with_base_path(settings: Settings, downloader: FakeDownloader) -> None:
    with _client(settings, downloader, "/tubevault/") as client:
        root = client.get("/tubevault/")
        assert root.status_code == 200
        assert '<base href="/tubevault/" />' in root.text
        assert root.headers["cache-control"] == "no-cache"
        assert root.headers["x-content-type-options"] == "nosniff"

        deep = client.get("/tubevault/videos/12")
        assert deep.status_code == 200 and "<base" in deep.text

        redirect = client.get("/tubevault", follow_redirects=False)
        assert redirect.status_code == 308
        assert redirect.headers["location"] == "/tubevault/"

        asset = client.get("/tubevault/assets/app-123.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        assert client.get("/tubevault/favicon.svg").text == "<svg/>"

        # Works with and without the prefix (proxy may strip it).
        assert client.get("/tubevault/api/health").json() == {"status": "ok"}
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/tubevault/api/nope").status_code == 404
        assert client.get("/tubevault/../config/tubevault.db").status_code in (200, 404)
        assert "SQLite" not in client.get("/tubevault/..%2Fconfig%2Ftubevault.db").text


def test_forwarded_prefix(settings: Settings, downloader: FakeDownloader) -> None:
    with _client(settings, downloader, "") as client:
        page = client.get("/", headers={"X-Forwarded-Prefix": "/media-server"})
        assert '<base href="/media-server/" />' in page.text
        evil = client.get("/", headers={"X-Forwarded-Prefix": '/"><script>'})
        assert '<base href="/" />' in evil.text
