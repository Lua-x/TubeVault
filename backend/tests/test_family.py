"""Family devices and "Wer schaut?": switching profiles with a tap, behind PINs."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.services.family import FAMILY_COOKIE
from tests.conftest import HEADERS
from tests.test_access import _login


def _user(admin: TestClient, username: str, **fields: Any) -> int:
    response = admin.post(
        "/api/users", json={"username": username, "password": "passwort1", **fields}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _tv(admin: TestClient) -> TestClient:
    """A second browser that only carries the family-device cookie (the TV)."""
    tv = TestClient(admin.app, headers=HEADERS)
    tv.cookies.set(FAMILY_COOKIE, admin.cookies[FAMILY_COOKIE])
    return tv


def test_only_family_devices_offer_profiles(admin: TestClient) -> None:
    stranger = TestClient(admin.app, headers=HEADERS)
    assert stranger.get("/api/family/profiles").status_code == 403
    assert stranger.post("/api/family/switch", json={"user_id": 1}).status_code == 403
    assert admin.get("/api/auth/status").json()["family_device"] is None

    viewer = _login(admin, "gast")
    assert viewer.post("/api/family/devices", json={"name": "Tablet"}).status_code == 403
    token = admin.post("/api/auth/tokens", json={"name": "Skript", "scope": "full"}).json()
    by_token = TestClient(admin.app, headers={"Authorization": f"Bearer {token['token']}"})
    assert by_token.post("/api/family/devices", json={"name": "x"}).status_code in (401, 403)

    created = admin.post("/api/family/devices", json={"name": "Wohnzimmer"})
    assert created.status_code == 201 and created.json()["current"] is True
    assert admin.get("/api/auth/status").json()["family_device"] == "Wohnzimmer"
    devices = admin.get("/api/family/devices").json()
    assert [(d["name"], d["current"]) for d in devices] == [("Wohnzimmer", True)]


def test_who_is_watching(admin: TestClient) -> None:
    admin.post("/api/family/devices", json={"name": "Wohnzimmer"})
    kid = _user(admin, "kind", on_family_devices=True)
    mum = _user(admin, "mama", on_family_devices=True, pin="1234")
    dad = _user(admin, "papa")
    me = admin.get("/api/auth/me").json()

    # Admins only appear with a PIN; PINs are 4 to 8 digits.
    no_pin = admin.put("/api/auth/me/family", json={"on_family_devices": True})
    assert no_pin.status_code == 422 and "PIN" in no_pin.json()["detail"]
    assert admin.put("/api/auth/me/family", json={"pin": "12"}).status_code == 422
    assert admin.put("/api/auth/me/family", json={"pin": "12ab"}).status_code == 422
    done = admin.put("/api/auth/me/family", json={"on_family_devices": True, "pin": "2468"})
    assert done.status_code == 200
    assert done.json()["has_pin"] is True and done.json()["on_family_devices"] is True

    tv = _tv(admin)
    profiles = tv.get("/api/family/profiles").json()
    assert [(p["username"], p["has_pin"]) for p in profiles] == [
        ("admin", True),
        ("kind", False),
        ("mama", True),
    ]

    # A profile without PIN: one tap.
    switched = tv.post("/api/family/switch", json={"user_id": kid})
    assert switched.status_code == 200 and switched.json()["username"] == "kind"
    assert tv.get("/api/auth/me").json()["username"] == "kind"
    kid_session = tv.cookies.get("tubevault_session")

    # Not on family devices, or a wrong PIN: no way in.
    assert tv.post("/api/family/switch", json={"user_id": dad}).status_code == 404
    assert tv.post("/api/family/switch", json={"user_id": mum}).status_code == 401
    assert tv.post("/api/family/switch", json={"user_id": mum, "pin": "0000"}).status_code == 401

    # The profile before is signed out when another one takes over.
    assert (
        tv.post("/api/family/switch", json={"user_id": me["id"], "pin": "2468"}).status_code == 200
    )
    stale = TestClient(admin.app, headers=HEADERS)
    stale.cookies.set("tubevault_session", kid_session or "")
    assert stale.get("/api/auth/me").status_code == 401

    # Guessing is slowed down: five wrong PINs, then even the right one waits.
    for _ in range(3):
        tv.post("/api/family/switch", json={"user_id": mum, "pin": "9999"})
    blocked = tv.post("/api/family/switch", json={"user_id": mum, "pin": "1234"})
    assert blocked.status_code == 429
    admin.app.state.ctx.pin_throttle.reset(f"pin:{mum}")  # type: ignore[attr-defined]
    assert tv.post("/api/family/switch", json={"user_id": mum, "pin": "1234"}).status_code == 200


def test_rights_changes_and_removing_a_device(admin: TestClient) -> None:
    admin.post("/api/family/devices", json={"name": "Wohnzimmer"})
    kid = _user(admin, "kind", on_family_devices=True)
    tv = _tv(admin)
    assert [p["username"] for p in tv.get("/api/family/profiles").json()] == ["kind"]

    # Made an admin without a PIN: gone from the TV until a PIN is set.
    assert admin.patch(f"/api/users/{kid}", json={"is_admin": True}).status_code == 200
    assert tv.get("/api/family/profiles").json() == []
    assert tv.post("/api/family/switch", json={"user_id": kid}).status_code == 404
    assert admin.patch(f"/api/users/{kid}", json={"pin": "4321"}).status_code == 200
    assert [p["username"] for p in tv.get("/api/family/profiles").json()] == ["kind"]

    # Removing the device ends it at once.
    device = admin.get("/api/family/devices").json()[0]
    assert admin.delete(f"/api/family/devices/{device['id']}").status_code == 204
    assert tv.get("/api/family/profiles").status_code == 403
    assert admin.get("/api/auth/status").json()["family_device"] is None
