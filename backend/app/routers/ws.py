"""WebSocket for live updates (download progress, new videos)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
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


@router.websocket("/ws")
async def events_socket(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    def authenticate() -> bool:
        with ctx.sessions() as db:
            return websocket_user(websocket, db, ctx.settings) is not None

    if not await asyncio.to_thread(authenticate):
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
                await websocket.send_json(event)
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
