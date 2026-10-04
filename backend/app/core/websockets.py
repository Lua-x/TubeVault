"""Shared pieces for the WebSocket endpoints: origin check, sign-in, message pump."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect

from app.core.context import AppContext
from app.core.deps import websocket_user
from app.services.rooms import Member

PING_INTERVAL = 25.0


def _hostname(value: str) -> str:
    """Host without port. Reverse proxies often forward `Host` without the port."""
    value = value.strip().lower()
    if value.startswith("["):  # IPv6 literal
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def origin_allowed(websocket: WebSocket) -> bool:
    """Browsers send cookies on cross-site WebSocket handshakes, so check the Origin."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True  # non-browser client
    origin_host = _hostname(urlparse(origin).netloc)
    candidates = [websocket.headers.get("host", "")]
    candidates += websocket.headers.get("x-forwarded-host", "").split(",")
    return origin_host in {_hostname(c) for c in candidates if c.strip()}


@dataclass(frozen=True)
class SocketUser:
    id: int
    username: str
    restricted: bool


async def socket_user(websocket: WebSocket, ctx: AppContext) -> SocketUser | None:
    def load() -> SocketUser | None:
        with ctx.sessions() as db:
            user = websocket_user(websocket, db, ctx.settings)
            return SocketUser(user.id, user.username, user.restricted) if user else None

    return await asyncio.to_thread(load)


async def pump(
    websocket: WebSocket,
    member: Member,
    on_message: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Sends the member's queue and hands incoming JSON objects over until one side ends."""

    async def write() -> None:
        while True:
            try:
                message = await asyncio.wait_for(member.queue.get(), timeout=PING_INTERVAL)
            except TimeoutError:
                message = {"type": "ping"}
            await websocket.send_json(message)
            if message.get("type") == "closed":
                return

    async def read() -> None:
        while True:
            try:
                data = await websocket.receive_json()
            except (ValueError, TypeError):
                continue  # not JSON: ignored
            if isinstance(data, dict):
                await on_message(data)

    tasks = [asyncio.create_task(write()), asyncio.create_task(read())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(
                asyncio.CancelledError, WebSocketDisconnect, RuntimeError, Exception
            ):
                await task
