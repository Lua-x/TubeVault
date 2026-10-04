"""Phone as a remote: pairing with the code from the TV, commands one way, state the other."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.test_access import _login


def _until(socket: Any, kind: str) -> dict[str, Any]:
    """The next message of a kind (skipping pings and other updates)."""
    for _ in range(20):
        message: dict[str, Any] = socket.receive_json()
        if message.get("type") == kind:
            return message
    raise AssertionError(f"no {kind} message")


def test_pair_steer_and_report(admin: TestClient) -> None:
    phone_client = _login(admin, "mama")
    with admin.websocket_connect("/api/remote/tv") as tv:
        code = _until(tv, "code")["code"]
        assert len(code) == 6 and code.isdigit()

        with phone_client.websocket_connect(f"/api/remote/phone?code={code}") as phone:
            assert _until(phone, "paired")["tv"] == "admin"
            joined = _until(tv, "phones")
            assert joined["joined"] == "mama" and [p["name"] for p in joined["phones"]] == ["mama"]

            # Commands reach the TV – checked and clamped.
            phone.send_json({"type": "command", "action": "skip", "value": 30})
            phone.send_json({"type": "command", "action": "seek", "value": -5})
            phone.send_json({"type": "command", "action": "open", "value": 7})
            phone.send_json({"type": "command", "action": "format_disk"})
            phone.send_json({"type": "command", "action": "open", "value": "7; drop"})
            phone.send_json({"type": "command", "action": "toggle"})
            received = [_until(tv, "command") for _ in range(4)]
            assert [(c["action"], c["value"]) for c in received] == [
                ("skip", 30.0),
                ("seek", 0.0),
                ("open", 7),
                ("toggle", None),
            ]
            assert received[0]["from"] == "mama"

            # The TV's state goes to the phone, unknown fields dropped.
            tv.send_json(
                {
                    "type": "state",
                    "video_id": 7,
                    "title": "Pasta",
                    "position": 12.5,
                    "duration": 300,
                    "paused": False,
                    "secret": "x",
                }
            )
            state = _until(phone, "state")
            assert state["title"] == "Pasta" and state["position"] == 12.5
            assert "secret" not in state

            # A second phone gets the last state right away.
            with phone_client.websocket_connect(f"/api/remote/phone?code={code}") as second:
                _until(second, "paired")
                assert _until(second, "state")["video_id"] == 7

            # The TV ends the pairing.
            tv.send_json({"type": "unpair"})
            closed = _until(phone, "closed")
            assert "getrennt" in closed["reason"]


def test_codes_are_checked_and_guessing_is_slowed(admin: TestClient) -> None:
    phone_client = _login(admin, "mama")
    with phone_client.websocket_connect("/api/remote/phone?code=000000") as phone:
        assert "Code" in _until(phone, "closed")["reason"]
    for _ in range(10):
        with phone_client.websocket_connect("/api/remote/phone?code=123456") as phone:
            phone.receive_json()
    with admin.websocket_connect("/api/remote/tv") as tv:
        code = _until(tv, "code")["code"]
        # Even the right code waits after too many wrong ones.
        with phone_client.websocket_connect(f"/api/remote/phone?code={code}") as phone:
            assert "Zu viele" in _until(phone, "closed")["reason"]
        # A new code from the TV makes the old one useless.
        tv.send_json({"type": "new_code"})
        fresh = _until(tv, "code")["code"]
        rooms = admin.app.state.ctx.rooms  # type: ignore[attr-defined]
        assert rooms.by_code(fresh) is not None
        assert fresh == code or rooms.by_code(code) is None

    # Without signing in: no socket at all.
    stranger = TestClient(admin.app)
    with pytest.raises(WebSocketDisconnect), stranger.websocket_connect("/api/remote/tv") as tv:
        tv.receive_json()


def test_room_closes_with_the_tv(admin: TestClient) -> None:
    phone_client = _login(admin, "mama")
    with admin.websocket_connect("/api/remote/tv") as tv:
        code = _until(tv, "code")["code"]
        phone_ctx = phone_client.websocket_connect(f"/api/remote/phone?code={code}")
        phone = phone_ctx.__enter__()
        _until(phone, "paired")
    # The TV is gone: the phone hears it, and the code is dead.
    assert "nicht mehr verbunden" in _until(phone, "closed")["reason"]
    phone_ctx.__exit__(None, None, None)
    assert admin.app.state.ctx.rooms.count == 0  # type: ignore[attr-defined]


def test_phone_comes_back_after_a_reload(admin: TestClient) -> None:
    phone_client = _login(admin, "mama")
    other = _login(admin, "papa")
    with admin.websocket_connect("/api/remote/tv") as tv:
        code = _until(tv, "code")["code"]
        with phone_client.websocket_connect(f"/api/remote/phone?code={code}") as phone:
            token = _until(phone, "paired")["token"]
        # Reloaded: the token brings the phone back, for its own account only.
        with phone_client.websocket_connect(f"/api/remote/phone?token={token}") as phone:
            assert _until(phone, "paired")["token"] == token
        with other.websocket_connect(f"/api/remote/phone?token={token}") as phone:
            assert _until(phone, "closed")
        # After the TV ended the pairing, the token is worthless.
        tv.send_json({"type": "unpair"})
        with phone_client.websocket_connect(f"/api/remote/phone?token={token}") as phone:
            assert _until(phone, "closed")
