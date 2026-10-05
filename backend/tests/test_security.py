"""Guards for 1.0: what is reachable without signing in, guessing, and bad backups."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.services import backups
from tests.conftest import HEADERS

# Everything else answers 401/403 without a sign-in. A new public route must be added here
# on purpose – and say what protects it instead.
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),  # rate-limited per address and per account
    ("POST", "/api/auth/login/2fa"),  # needs the ticket from a correct password
    ("POST", "/api/auth/setup"),  # only while there is no user at all
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/oidc/login"),  # state + PKCE, only when OIDC is set up
    ("GET", "/api/auth/oidc/callback"),
    # Signed, expiring links for the TV (HMAC, checked again against the account's rights).
    ("GET", "/api/cast/{user_id}/{video_id}/{expires}/{signature}.mp4"),
    ("HEAD", "/api/cast/{user_id}/{video_id}/{expires}/{signature}.mp4"),
    # Podcast apps can't sign in: a secret key in the address, with the user's rights.
    ("GET", "/api/podcast/{token}/audio/{video_id}.m4a"),
    ("GET", "/api/podcast/{token}/channels/{channel_id}.xml"),
    ("GET", "/api/podcast/{token}/images/channels/{channel_id}.jpg"),
    ("GET", "/api/podcast/{token}/images/videos/{video_id}.jpg"),
    ("GET", "/api/podcast/{token}/playlists/{playlist_id}.xml"),
}


def test_every_other_route_needs_a_sign_in(admin: TestClient) -> None:
    stranger = TestClient(admin.app, headers=HEADERS)
    spec = admin.app.openapi()  # type: ignore[attr-defined]
    open_routes = set()
    for path, operations in spec["paths"].items():
        for method in operations:
            url = re.sub(r"\{[^}]+\}", "1", path)
            response = stranger.request(method.upper(), url, json={})
            if response.status_code not in (401, 403):
                open_routes.add((method.upper(), path))
    assert open_routes == PUBLIC
    # Setup is closed once there is an admin.
    taken = stranger.post("/api/auth/setup", json={"username": "evil", "password": "geheim123"})
    assert taken.status_code in (403, 409)


def test_guessing_one_account_from_many_addresses(admin: TestClient) -> None:
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    guesser = TestClient(admin.app, headers=HEADERS)
    for _ in range(20):
        # A fresh address every time (as with a faked X-Forwarded-For) …
        ctx.login_throttle.reset("testclient")
        wrong = guesser.post("/api/auth/login", json={"username": "Admin", "password": "rate1234"})
        assert wrong.status_code == 401
    # … still ends at the account: even the right password waits now.
    ctx.login_throttle.reset("testclient")
    right = guesser.post("/api/auth/login", json={"username": "admin", "password": "geheim123"})
    assert right.status_code == 429
    ctx.account_throttle.reset("account:admin")
    assert guesser.post(
        "/api/auth/login", json={"username": "admin", "password": "geheim123"}
    ).is_success


def test_oversized_backups_are_refused(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    name = admin.post("/api/admin/backups").json()["name"]
    monkeypatch.setattr(backups, "MAX_DATABASE_BYTES", 1024)
    refused = admin.post(f"/api/admin/backups/{name}/restore")
    assert refused.status_code == 400 and "groß" in refused.json()["detail"]
    assert admin.get("/api/admin/backups").json()["staged"] is None
