from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.models import ApiToken
from tests.conftest import HEADERS, wait_for


def _bearer(client: TestClient, token: str) -> TestClient:
    """A client without cookies and without the CSRF header – like a script."""
    return TestClient(client.app, headers={"Authorization": f"Bearer {token}"})


def _create(admin: TestClient, **body: Any) -> dict[str, Any]:
    response = admin.post("/api/auth/tokens", json={"name": "Skript", **body})
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_read_token(admin: TestClient) -> None:
    created = _create(admin, scope="read")
    assert created["token"].startswith("tv_") and created["prefix"] == created["token"][:11]
    listed = admin.get("/api/auth/tokens").json()
    assert listed[0]["name"] == "Skript" and "token" not in listed[0]

    script = _bearer(admin, created["token"])
    assert script.get("/api/videos").status_code == 200
    denied = script.post("/api/videos", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert denied.status_code == 403 and "nur lesen" in denied.json()["detail"]
    assert admin.get("/api/auth/tokens").json()[0]["last_used_at"] is not None


def test_full_token_adds_videos_without_csrf_header(admin: TestClient) -> None:
    script = _bearer(admin, _create(admin, scope="full")["token"])
    response = script.post("/api/videos", json={"url": "https://youtu.be/tokenvideo1"})
    assert response.status_code == 202, response.text
    wait_for(lambda: admin.get("/api/videos").json()["total"] == 1)


def test_tokens_cannot_manage_the_account(admin: TestClient) -> None:
    script = _bearer(admin, _create(admin, scope="full")["token"])
    assert script.get("/api/auth/tokens").status_code == 403
    assert script.post("/api/auth/tokens", json={"name": "x"}).status_code == 403
    response = script.post(
        "/api/auth/me/password", json={"current_password": "x", "new_password": "y" * 10}
    )
    assert response.status_code == 403


def test_invalid_expired_and_revoked_tokens(admin: TestClient) -> None:
    assert _bearer(admin, "tv_nope").get("/api/videos").status_code == 401
    assert _bearer(admin, "kein-token").get("/api/videos").status_code == 401

    expiring = _create(admin, expires_days=30)
    assert expiring["expires_at"] is not None
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    with ctx.sessions() as db:
        token = db.get(ApiToken, expiring["id"])
        token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert _bearer(admin, expiring["token"]).get("/api/videos").status_code == 401

    revoked = _create(admin)
    assert admin.delete(f"/api/auth/tokens/{revoked['id']}").status_code == 204
    assert _bearer(admin, revoked["token"]).get("/api/videos").status_code == 401


def test_tokens_are_private(admin: TestClient) -> None:
    token = _create(admin)
    admin.post("/api/users", json={"username": "mia", "password": "passwort1"})
    other = TestClient(admin.app, headers=HEADERS)
    other.post("/api/auth/login", json={"username": "mia", "password": "passwort1"})
    assert other.get("/api/auth/tokens").json() == []
    assert other.delete(f"/api/auth/tokens/{token['id']}").status_code == 404
    assert admin.post("/api/auth/tokens", json={"name": "   "}).status_code == 422
