from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import totp
from app.models import User
from tests.conftest import HEADERS


def test_rfc6238_vectors() -> None:
    # RFC 6238, appendix B (SHA-1, secret "12345678901234567890"), 8 digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    for unix, expected in [(59, "94287082"), (1111111109, "07081804"), (2000000000, "69279037")]:
        assert totp.code_at(secret, unix // 30, digits=8) == expected
    code = totp.code_at(secret, totp.current_counter(1000))
    assert totp.verify(secret, code, now=1000) == totp.current_counter(1000)
    assert totp.verify(secret, code, now=1000 + 30) is not None  # clock drift
    assert totp.verify(secret, code, now=1000 + 90) is None
    assert totp.verify(secret, code, now=1000, last_counter=totp.current_counter(1000)) is None
    uri = totp.otpauth_uri("ABC", "lukas")
    assert uri.startswith("otpauth://totp/TubeVault%3Alukas?secret=ABC")


def _now_code(secret: str, offset: int = 0) -> str:
    return totp.code_at(secret, totp.current_counter() + offset)


def _enable(client: TestClient) -> tuple[str, list[str]]:
    setup = client.post("/api/auth/2fa/setup").json()
    assert setup["uri"].startswith("otpauth://")
    assert client.post("/api/auth/2fa/enable", json={"code": "000000"}).status_code == 400
    enabled = client.post("/api/auth/2fa/enable", json={"code": _now_code(setup["secret"])})
    assert enabled.status_code == 200, enabled.text
    codes = enabled.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    return setup["secret"], codes


def _login(app: Any) -> tuple[TestClient, dict[str, Any]]:
    client = TestClient(app, headers=HEADERS)
    response = client.post("/api/auth/login", json={"username": "admin", "password": "geheim123"})
    assert response.status_code == 200, response.text
    return client, response.json()


def test_login_needs_the_code(admin: TestClient) -> None:
    secret, codes = _enable(admin)
    status = admin.get("/api/auth/2fa").json()
    assert status == {"enabled": True, "recovery_codes_left": 10}
    assert admin.get("/api/auth/me").json()["two_factor"] is True

    client, first = _login(admin.app)
    assert first["two_factor"] is True and "id" not in first
    assert client.get("/api/auth/me").status_code == 401  # no session yet
    wrong = client.post("/api/auth/login/2fa", json={"ticket": first["ticket"], "code": "123456"})
    assert wrong.status_code == 401
    # The code used for enabling cannot be replayed; the next one works.
    ok = client.post(
        "/api/auth/login/2fa", json={"ticket": first["ticket"], "code": _now_code(secret, 1)}
    )
    assert ok.status_code == 200 and ok.json()["username"] == "admin"
    assert client.get("/api/auth/me").status_code == 200
    again = client.post(
        "/api/auth/login/2fa", json={"ticket": first["ticket"], "code": _now_code(secret, 1)}
    )
    assert again.status_code == 401  # ticket used up

    # Recovery codes work once each.
    other, challenge = _login(admin.app)
    used = other.post(
        "/api/auth/login/2fa", json={"ticket": challenge["ticket"], "code": codes[0].upper()}
    )
    assert used.status_code == 200
    third, challenge = _login(admin.app)
    reused = third.post(
        "/api/auth/login/2fa", json={"ticket": challenge["ticket"], "code": codes[0]}
    )
    assert reused.status_code == 401
    assert other.get("/api/auth/2fa").json()["recovery_codes_left"] == 9


def test_ticket_allows_only_a_few_tries(admin: TestClient) -> None:
    _enable(admin)
    client, challenge = _login(admin.app)
    for _ in range(5):
        client.post("/api/auth/login/2fa", json={"ticket": challenge["ticket"], "code": "000000"})
    with admin.app.state.ctx.sessions() as db:  # type: ignore[attr-defined]
        secret = db.query(User).filter_by(username="admin").one().totp_secret
    late = client.post(
        "/api/auth/login/2fa",
        json={"ticket": challenge["ticket"], "code": _now_code(secret, 1)},
    )
    assert late.status_code == 401 and "abgelaufen" in late.json()["detail"]


def test_disable_and_new_recovery_codes(admin: TestClient) -> None:
    secret, codes = _enable(admin)
    assert admin.post("/api/auth/2fa/disable", json={"code": "111111"}).status_code == 400
    new = admin.post("/api/auth/2fa/recovery-codes", json={"code": codes[1]})
    assert new.status_code == 200 and new.json()["recovery_codes"][0] not in codes
    assert admin.post("/api/auth/2fa/disable", json={"code": codes[2]}).status_code == 400
    disabled = admin.post("/api/auth/2fa/disable", json={"code": _now_code(secret, 1)})
    assert disabled.status_code == 204
    _client, response = _login(admin.app)
    assert response["username"] == "admin"  # plain login again


def test_admin_resets_a_lost_phone(admin: TestClient) -> None:
    admin.post("/api/users", json={"username": "mia", "password": "passwort1"})
    mia = TestClient(admin.app, headers=HEADERS)
    mia.post("/api/auth/login", json={"username": "mia", "password": "passwort1"})
    _enable(mia)
    mia_id = mia.get("/api/auth/me").json()["id"]
    users = {u["username"]: u for u in admin.get("/api/users").json()}
    assert users["mia"]["two_factor"] is True
    assert mia.delete(f"/api/users/{mia_id}/2fa").status_code == 403
    assert admin.delete(f"/api/users/{mia_id}/2fa").status_code == 204
    fresh = TestClient(admin.app, headers=HEADERS)
    plain = fresh.post("/api/auth/login", json={"username": "mia", "password": "passwort1"})
    assert plain.json()["username"] == "mia"


def test_tokens_and_enabling_signs_out_other_devices(admin: TestClient) -> None:
    laptop, _ = _login(admin.app)
    assert laptop.get("/api/auth/me").status_code == 200
    _enable(admin)
    assert laptop.get("/api/auth/me").status_code == 401
    assert admin.get("/api/auth/me").status_code == 200


def test_cli_reset(settings: Any, admin: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    from app import __main__ as cli

    _enable(admin)
    assert cli.reset_two_factor(settings, "admin") == 0
    assert "ausgeschaltet" in capsys.readouterr().out
    assert cli.reset_two_factor(settings, "niemand") == 1
