"""Phone as a remote for the TV view: pairing with a code from the screen, then commands.

The TV keeps a socket open and shows a six-digit code (or a QR code). A phone signed in
to TubeVault joins with that code and sends commands; the TV reports what is playing.
The TV opens videos with its own account – a kids profile stays a kids profile, whoever
holds the phone.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, WebSocket

from app.core.context import AppContext
from app.core.websockets import origin_allowed, pump, socket_user
from app.services.rooms import CODE_TTL_S, Member, Room

router = APIRouter(prefix="/remote", tags=["remote"])

ACTIONS = {"toggle", "play", "pause", "seek", "skip", "next", "previous", "open", "back"}


def _command(data: dict[str, Any]) -> dict[str, Any] | None:
    """A phone's command, checked – anything else is dropped."""
    action = data.get("action")
    if data.get("type") != "command" or action not in ACTIONS:
        return None
    value = data.get("value")
    if action in ("seek", "skip"):
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            return None
        limit = 10**6 if action == "seek" else 3600
        value = max(-limit if action == "skip" else 0, min(limit, float(value)))
    elif action == "open":
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return None
    else:
        value = None
    return {"type": "command", "action": action, "value": value}


def _state(data: dict[str, Any]) -> dict[str, Any]:
    """What the TV reports, reduced to plain fields."""
    allowed: dict[str, type | tuple[type, ...]] = {
        "video_id": int,
        "title": str,
        "channel": str,
        "position": (int, float),
        "duration": (int, float),
        "paused": bool,
        "has_next": bool,
        "has_previous": bool,
    }
    state: dict[str, Any] = {"type": "state"}
    for key, kind in allowed.items():
        value = data.get(key)
        if isinstance(value, kind) and not (kind is not bool and isinstance(value, bool)):
            state[key] = value[:300] if isinstance(value, str) else value
    return state


@router.websocket("/tv")
async def tv_socket(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    user = await socket_user(websocket, ctx)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    rooms = ctx.rooms
    room = rooms.create("remote", user.id)
    tv = Member(user.id, user.username, "tv")
    rooms.join(room, tv)

    def announce_code() -> None:
        tv.send({"type": "code", "code": rooms.new_code(room), "expires_in": CODE_TTL_S})

    def phones() -> list[dict[str, Any]]:
        return [{"id": m.id, "name": m.username} for m in room.with_role("phone")]

    announce_code()

    async def on_message(data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "state":
            room.state = _state(data)
            rooms.broadcast(room, room.state, roles=("phone",))
        elif kind == "new_code":
            announce_code()
        elif kind == "unpair":
            rooms.drop_tokens(room)
            for phone in room.with_role("phone"):
                phone.send(
                    {"type": "closed", "reason": "Der Fernseher hat die Verbindung getrennt."}
                )
                rooms.leave(room, phone)
            tv.send({"type": "phones", "phones": phones()})

    try:
        await pump(websocket, tv, on_message)
    finally:
        rooms.broadcast(
            room,
            {"type": "closed", "reason": "Der Fernseher ist nicht mehr verbunden."},
            roles=("phone",),
        )
        for member in list(room.members):
            rooms.leave(room, member)


def _room_for_code(ctx: AppContext, code: str) -> Room | None:
    return ctx.rooms.by_code(code) if code.isdigit() and len(code) == 6 else None


@router.websocket("/phone")
async def phone_socket(websocket: WebSocket, code: str = "", token: str = "") -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    user = await socket_user(websocket, ctx)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    key = f"remote:{user.id}"
    throttle = ctx.remote_throttle
    if token:
        # Back after a reload: no code needed while the TV is still there.
        rejoined = ctx.rooms.by_token(token, user.id) if len(token) < 64 else None
        if rejoined is None:
            await websocket.send_json(
                {"type": "closed", "reason": "Der Fernseher ist nicht mehr verbunden."}
            )
            await websocket.close(code=4404)
            return
        room: Room | None = rejoined
    else:
        room = None if throttle.is_blocked(key) else _room_for_code(ctx, code)
    if room is None:
        if not throttle.is_blocked(key):
            throttle.record_failure(key)
        message = (
            "Zu viele falsche Codes. Bitte in ein paar Minuten erneut versuchen."
            if throttle.is_blocked(key)
            else "Diesen Code kennt TubeVault nicht – vielleicht ist er abgelaufen."
        )
        await websocket.send_json({"type": "closed", "reason": message})
        await websocket.close(code=4404)
        return
    throttle.reset(key)
    rooms = ctx.rooms
    phone = Member(user.id, user.username, "phone")
    rooms.join(room, phone)
    tv_name = next((m.username for m in room.with_role("tv")), "")
    phone.send(
        {"type": "paired", "tv": tv_name, "token": token or rooms.issue_token(room, user.id)}
    )
    if room.state:
        phone.send(room.state)
    phone_list = [{"id": m.id, "name": m.username} for m in room.with_role("phone")]
    rooms.broadcast(
        room, {"type": "phones", "phones": phone_list, "joined": user.username}, roles=("tv",)
    )

    async def on_message(data: dict[str, Any]) -> None:
        command = _command(data)
        if command is not None:
            rooms.broadcast(room, {**command, "from": user.username}, roles=("tv",))

    try:
        await pump(websocket, phone, on_message)
    finally:
        rooms.leave(room, phone)
        if room.with_role("tv"):
            remaining = [{"id": m.id, "name": m.username} for m in room.with_role("phone")]
            rooms.broadcast(room, {"type": "phones", "phones": remaining}, roles=("tv",))
