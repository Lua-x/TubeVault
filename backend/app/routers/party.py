"""Watching together: everyone in a room sees the same moment of the same video.

Whoever presses play, pause or seeks, the others follow. The server keeps the playback
state and sends it to everyone every few seconds, so players that drift (buffering, a
slow phone) catch up. Only signed-in accounts that may see the video can join.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, status
from pydantic import BaseModel

from app.core.context import AppContext
from app.core.deps import Context, CurrentUser, DbSession
from app.core.websockets import origin_allowed, pump, socket_user
from app.models import User, Video
from app.services.access import can_see_video, ensure_visible
from app.services.rooms import Member, Room, RoomError

router = APIRouter(prefix="/party", tags=["party"])

HEARTBEAT_S = 4.0
_heartbeats: dict[str, asyncio.Task[None]] = {}


class PartyIn(BaseModel):
    video_id: int


class PartyOut(BaseModel):
    id: str
    video_id: int


@router.post("", status_code=status.HTTP_201_CREATED)
def create_party(body: PartyIn, user: CurrentUser, db: DbSession, ctx: Context) -> PartyOut:
    video = ensure_visible(user, db.get(Video, body.video_id))
    try:
        room = ctx.rooms.create("party", user.id, video.id)
    except RoomError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    room.state = {"paused": True, "position": 0.0, "updated": time.monotonic()}
    return PartyOut(id=room.id, video_id=video.id)


def _now(room: Room) -> dict[str, Any]:
    """The state as of now: a playing video has moved on since the last action."""
    state = room.state or {"paused": True, "position": 0.0, "updated": time.monotonic()}
    position = float(state["position"])
    if not state["paused"]:
        position += time.monotonic() - float(state["updated"])
    return {"paused": bool(state["paused"]), "position": round(position, 2)}


async def _heartbeat(ctx: AppContext, room: Room) -> None:
    while ctx.rooms.get(room.id) is room:
        await asyncio.sleep(HEARTBEAT_S)
        if not room.members:
            return
        ctx.rooms.broadcast(room, {"type": "tick", **_now(room)})


def _presence(ctx: AppContext, room: Room) -> dict[str, Any]:
    return {"type": "presence", "members": ctx.rooms.presence(room)}


@router.websocket("/{room_id}")
async def party_socket(websocket: WebSocket, room_id: str) -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    user = await socket_user(websocket, ctx)
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    room = ctx.rooms.get(room_id)
    if room is None or room.kind != "party" or room.video_id is None:
        await websocket.send_json({"type": "closed", "reason": "Diesen Raum gibt es nicht mehr."})
        await websocket.close(code=4404)
        return
    video_id = room.video_id

    def allowed() -> bool:
        with ctx.sessions() as db:
            account, video = db.get(User, user.id), db.get(Video, video_id)
            return account is not None and video is not None and can_see_video(account, video)

    if not await asyncio.to_thread(allowed):
        await websocket.send_json(
            {"type": "closed", "reason": "Dieses Video ist für dein Konto nicht freigegeben."}
        )
        await websocket.close(code=4403)
        return

    host = user.id == room.owner_id and not room.with_role("host")
    member = Member(user.id, user.username, "host" if host else "guest")
    ctx.rooms.join(room, member)
    if room.id not in _heartbeats or _heartbeats[room.id].done():
        _heartbeats[room.id] = asyncio.create_task(_heartbeat(ctx, room))
    member.send({"type": "joined", "you": member.id, "video_id": video_id, **_now(room)})
    ctx.rooms.broadcast(room, _presence(ctx, room))

    async def on_message(data: dict[str, Any]) -> None:
        if data.get("type") != "sync" or data.get("action") not in ("play", "pause", "seek"):
            return
        position = data.get("position")
        if not isinstance(position, int | float) or isinstance(position, bool):
            return
        if not math.isfinite(position) or not 0 <= position <= 10**6:
            return
        action = data["action"]
        paused = action == "pause" or (action == "seek" and _now(room)["paused"])
        room.state = {"paused": paused, "position": float(position), "updated": time.monotonic()}
        ctx.rooms.broadcast(
            room,
            {"type": "sync", "action": action, "by": user.username, **_now(room)},
            exclude=member,
        )

    try:
        await pump(websocket, member, on_message)
    finally:
        ctx.rooms.leave(room, member)
        if room.members:
            ctx.rooms.broadcast(room, _presence(ctx, room))
        else:
            task = _heartbeats.pop(room.id, None)
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
