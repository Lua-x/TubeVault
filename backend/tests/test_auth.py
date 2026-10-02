from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import HEADERS, FakeDownloader


def test_setup_flow(client: TestClient) -> None:
    status = client.get("/api/auth/status").json()
    assert status == {"setup_required": True, "user": None}

    response = client.post("/api/auth/setup", json={"username": "Admin", "password": "geheim123"})
    assert response.status_code == 201
    assert response.json()["is_admin"] is True
    assert client.get("/api/auth/me").json()["username"] == "Admin"

    again = client.post("/api/auth/setup", json={"username": "other", "password": "geheim123"})
    assert again.status_code == 409


def test_setup_rejects_short_password(client: TestClient) -> None:
    response = client.post("/api/auth/setup", json={"username": "admin", "password": "kurz"})
    assert response.status_code == 422


def test_login_logout(admin: TestClient) -> None:
    admin.post("/api/auth/logout")
    assert admin.get("/api/auth/me").status_code == 401

    wrong = admin.post("/api/auth/login", json={"username": "admin", "password": "falsch"})
    assert wrong.status_code == 401

    ok = admin.post("/api/auth/login", json={"username": "ADMIN", "password": "geheim123"})
    assert ok.status_code == 200
    assert "tubevault_session" in ok.cookies
    assert admin.get("/api/auth/me").status_code == 200


def test_unsafe_requests_need_csrf_header(admin: TestClient) -> None:
    bare = TestClient(admin.app)  # no default X-Requested-With header
    bare.cookies = admin.cookies
    assert bare.post("/api/auth/logout").status_code == 403
    assert bare.get("/api/auth/me").status_code == 200  # safe methods are fine


def test_login_throttle(admin: TestClient) -> None:
    for _ in range(10):
        admin.post("/api/auth/login", json={"username": "admin", "password": "falsch"})
    blocked = admin.post("/api/auth/login", json={"username": "admin", "password": "geheim123"})
    assert blocked.status_code == 429


def test_admin_from_environment(settings: Settings, downloader: FakeDownloader) -> None:
    settings.admin_user = "root"
    settings.admin_password = "supergeheim"
    app = create_app(settings, downloader, configure_logging=False)
    with TestClient(app, headers=HEADERS) as client:
        assert client.get("/api/auth/status").json()["setup_required"] is False
        ok = client.post("/api/auth/login", json={"username": "root", "password": "supergeheim"})
        assert ok.status_code == 200
        assert ok.json()["is_admin"] is True


def test_user_management(admin: TestClient) -> None:
    created = admin.post(
        "/api/users", json={"username": "lisa", "password": "passwort1", "is_admin": False}
    )
    assert created.status_code == 201
    duplicate = admin.post("/api/users", json={"username": "LISA", "password": "passwort1"})
    assert duplicate.status_code == 409

    admin.post("/api/auth/logout")
    admin.post("/api/auth/login", json={"username": "lisa", "password": "passwort1"})
    assert admin.get("/api/users").status_code == 403
    assert admin.get("/api/videos").status_code == 200


def test_last_admin_cannot_be_demoted(admin: TestClient) -> None:
    me = admin.get("/api/auth/me").json()
    response = admin.patch(f"/api/users/{me['id']}", json={"is_admin": False})
    assert response.status_code == 400


def test_preferences_and_password(admin: TestClient) -> None:
    prefs = admin.put("/api/auth/me/preferences", json={"theme": "light"})
    assert prefs.json()["preferences"]["theme"] == "light"

    bad = admin.post(
        "/api/auth/me/password", json={"current_password": "x", "new_password": "neuespasswort"}
    )
    assert bad.status_code == 400
    ok = admin.post(
        "/api/auth/me/password",
        json={"current_password": "geheim123", "new_password": "neuespasswort"},
    )
    assert ok.status_code == 204
    admin.post("/api/auth/logout")
    login = admin.post("/api/auth/login", json={"username": "admin", "password": "neuespasswort"})
    assert login.status_code == 200
