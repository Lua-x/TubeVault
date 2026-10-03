"""WebSocket for live updates (download progress, new videos)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.context import AppContext
from app.core.deps import websocket_user

router = APIRouter()
log = logging.getLogger(__name__)

PING_INTERVAL = 25.0


def _hostname(value: str) -> str:
    """Host without port. Reverse proxies often forward `Host` without the port."""
    value = value.strip().lower()
    if value.startswith("["):  # IPv6 literal
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _origin_allowed(websocket: WebSocket) -> bool:
    """Browsers send cookies on cross-site WebSocket handshakes, so check the Origin."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True  # non-browser client
    origin_host = _hostname(urlparse(origin).netloc)
    candidates = [websocket.headers.get("host", "")]
    candidates += websocket.headers.get("x-forwarded-host", "").split(",")
    return origin_host in {_hostname(c) for c in candidates if c.strip()}


# What a restricted account (e.g. a kids profile) still hears: that something changed,
# not what – download and subscription events carry titles from every channel.
RESTRICTED_EVENTS = {"video.updated", "video.deleted", "video.comments", "channels.updated", "ping"}


def event_for(event: dict[str, Any], *, restricted: bool) -> dict[str, Any] | None:
    if not restricted:
        return event
    kind = event.get("type")
    return {"type": kind} if kind in RESTRICTED_EVENTS else None


@router.websocket("/ws")
async def events_socket(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    def authenticate() -> tuple[bool, bool]:
        with ctx.sessions() as db:
            user = websocket_user(websocket, db, ctx.settings)
            return user is not None, bool(user and user.restricted)

    authenticated, restricted = await asyncio.to_thread(authenticate)
    if not authenticated:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    async with ctx.events.subscribe() as queue:
        receiver = asyncio.create_task(_drain(websocket))
        try:
            while not receiver.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL)
                except TimeoutError:
                    event = {"type": "ping"}
                visible = event_for(event, restricted=restricted)
                if visible is not None:
                    await websocket.send_json(visible)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await receiver


async def _drain(websocket: WebSocket) -> None:
    """Read (and ignore) client messages so disconnects are noticed."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await websocket.receive_text()
