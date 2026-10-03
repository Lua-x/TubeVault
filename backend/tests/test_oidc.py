"""OIDC login against a fake provider: the full flow and every check on the ID token."""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import oidc
from tests.conftest import HEADERS

ISSUER = "https://auth.example.org"


class FakeProvider:
    def __init__(self) -> None:
        self.claims: dict[str, Any] = {"sub": "u-123", "preferred_username": "lukas"}
        self.userinfo: dict[str, Any] = {}
        self.token_requests: list[tuple[dict[str, str], dict[str, str]]] = []
        self.override: dict[str, Any] = {}
        self.nonce = ""

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "userinfo_endpoint": f"{ISSUER}/userinfo",
            }
        assert url == f"{ISSUER}/userinfo" and headers == {"Authorization": "Bearer at"}
        return {"sub": self.claims["sub"], **self.userinfo}

    def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
        assert url == f"{ISSUER}/token"
        self.token_requests.append((form, headers))
        payload = {
            "iss": ISSUER,
            "aud": "tubevault",
            "exp": int(time.time()) + 300,
            "nonce": self.nonce,
            **self.claims,
            **self.override,
        }
        encode = lambda data: base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=")  # noqa: E731
        token = b".".join([encode({"alg": "RS256"}), encode(payload), b"sig"]).decode()
        return {"id_token": token, "access_token": "at"}


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> FakeProvider:
    fake = FakeProvider()
    monkeypatch.setattr(oidc, "http_get_json", fake.get_json)
    monkeypatch.setattr(oidc, "http_post_form", fake.post_form)
    settings.oidc_issuer = ISSUER
    settings.oidc_client_id = "tubevault"
    settings.oidc_client_secret = "geheim"
    settings.oidc_name = "Authelia"
    settings.public_url = "https://tube.example.org"
    return fake


def _start(client: TestClient, provider: FakeProvider, path: str = "/api/auth/oidc/login") -> str:
    response = client.get(path, params={"next": "/library"}, follow_redirects=False)
    assert response.status_code == 303, response.text
    location = urllib.parse.urlparse(response.headers["location"])
    query = dict(urllib.parse.parse_qsl(location.query))
    assert location.netloc == "auth.example.org" and query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == "https://tube.example.org/api/auth/oidc/callback"
    provider.nonce = query["nonce"]
    return query["state"]


def _callback(client: TestClient, state: str) -> Any:
    return client.get(
        "/api/auth/oidc/callback", params={"code": "c0de", "state": state}, follow_redirects=False
    )


def _error(response: Any) -> str:
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(response.headers["location"]).query))
    return query.get("oidc_error", "")


def test_login_creates_the_account(admin: TestClient, provider: FakeProvider) -> None:
    status = TestClient(admin.app, headers=HEADERS).get("/api/auth/status").json()
    assert status["oidc_name"] == "Authelia" and status["password_login"] is True

    browser = TestClient(admin.app, headers=HEADERS)
    response = _callback(browser, _start(browser, provider))
    assert response.status_code == 303 and response.headers["location"] == "/library"
    me = browser.get("/api/auth/me").json()
    assert me["username"] == "lukas" and me["oidc_linked"] is True
    assert me["has_password"] is False and me["is_admin"] is False

    form, headers = provider.token_requests[0]
    assert form["code"] == "c0de" and form["code_verifier"]
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"tubevault:geheim").decode()

    # The same person again: the same account, no duplicate.
    again = TestClient(admin.app, headers=HEADERS)
    _callback(again, _start(again, provider))
    assert again.get("/api/auth/me").json()["id"] == me["id"]
    assert len(admin.get("/api/users").json()) == 2
    # No password: it can never log in with one.
    bad = again.post("/api/auth/login", json={"username": "lukas", "password": ""})
    assert bad.status_code == 422 or bad.status_code == 401


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"iss": "https://evil.example"}, "anderen Aussteller"),
        ({"aud": "something-else"}, "andere Anwendung"),
        ({"exp": int(time.time()) - 3600}, "abgelaufen"),
        ({"nonce": "wrong"}, "passt nicht"),
    ],
)
def test_token_checks(
    admin: TestClient, provider: FakeProvider, override: dict[str, Any], message: str
) -> None:
    provider.override = override
    browser = TestClient(admin.app, headers=HEADERS)
    response = _callback(browser, _start(browser, provider))
    assert response.headers["location"].startswith("/login?") and message in _error(response)
    assert browser.get("/api/auth/me").status_code == 401


def test_state_is_single_use(admin: TestClient, provider: FakeProvider) -> None:
    browser = TestClient(admin.app, headers=HEADERS)
    state = _start(browser, provider)
    assert _callback(browser, state).headers["location"] == "/library"
    assert "abgelaufen" in _error(_callback(browser, state))
    assert "abgelaufen" in _error(_callback(browser, "made-up"))
    denied = browser.get(
        "/api/auth/oidc/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert "access_denied" in _error(denied)


def test_admin_group_and_userinfo(
    admin: TestClient, provider: FakeProvider, settings: Settings
) -> None:
    settings.oidc_admin_group = "tubevault-admins"
    provider.userinfo = {"groups": ["family", "tubevault-admins"]}  # only in userinfo
    browser = TestClient(admin.app, headers=HEADERS)
    _callback(browser, _start(browser, provider))
    assert browser.get("/api/auth/me").json()["is_admin"] is True

    provider.userinfo = {"groups": ["family"]}
    again = TestClient(admin.app, headers=HEADERS)
    _callback(again, _start(again, provider))
    assert again.get("/api/auth/me").json()["is_admin"] is False


def test_no_auto_create_and_linking(
    admin: TestClient, provider: FakeProvider, settings: Settings
) -> None:
    settings.oidc_auto_create = False
    stranger = TestClient(admin.app, headers=HEADERS)
    refused = _callback(stranger, _start(stranger, provider))
    assert "noch keinen Benutzer" in _error(refused)

    # The signed-in admin links their own account …
    state = _start(admin, provider, "/api/auth/oidc/link")
    linked = _callback(admin, state)
    assert linked.headers["location"] == "/settings?oidc=linked"
    assert admin.get("/api/auth/me").json()["oidc_linked"] is True
    # … and from now on the provider logs into exactly that account.
    browser = TestClient(admin.app, headers=HEADERS)
    _callback(browser, _start(browser, provider))
    assert browser.get("/api/auth/me").json()["username"] == "admin"

    # Linking the same provider account to another user is refused.
    admin.post("/api/users", json={"username": "mia", "password": "passwort1"})
    mia = TestClient(admin.app, headers=HEADERS)
    mia.post("/api/auth/login", json={"username": "mia", "password": "passwort1"})
    clash = _callback(mia, _start(mia, provider, "/api/auth/oidc/link"))
    assert clash.headers["location"].startswith("/settings?") and "schon" in _error(clash)

    assert admin.post("/api/auth/oidc/unlink").status_code == 204
    assert admin.get("/api/auth/me").json()["oidc_linked"] is False


def test_account_without_password(admin: TestClient, provider: FakeProvider) -> None:
    browser = TestClient(admin.app, headers=HEADERS)
    _callback(browser, _start(browser, provider))
    # Unlinking would lock it out …
    assert browser.post("/api/auth/oidc/unlink").status_code == 400
    # … until it sets a password (no current one needed for that).
    response = browser.post("/api/auth/me/password", json={"new_password": "neuespasswort"})
    assert response.status_code == 204
    assert browser.post("/api/auth/oidc/unlink").status_code == 204


def test_password_login_can_be_turned_off(
    admin: TestClient, provider: FakeProvider, settings: Settings
) -> None:
    settings.password_login = False
    browser = TestClient(admin.app, headers=HEADERS)
    assert browser.get("/api/auth/status").json()["password_login"] is False
    refused = browser.post("/api/auth/login", json={"username": "admin", "password": "geheim123"})
    assert refused.status_code == 403
    # Without a configured provider the switch is ignored – nobody gets locked out.
    settings.oidc_client_secret = None
    assert browser.get("/api/auth/status").json()["password_login"] is True


def test_open_redirects_are_impossible() -> None:
    for bad in ("https://evil.example", "//evil.example", "/\\evil", "", None):
        assert oidc.safe_next(bad) == "/"
    assert oidc.safe_next("/videos/3?t=10") == "/videos/3?t=10"


def test_not_configured(client: TestClient) -> None:
    assert client.get("/api/auth/status").json()["oidc_name"] is None
    assert client.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404
