"""Live rooms: a TV and the phones steering it, or friends watching a video together.

Everything lives in memory on the server's event loop (the WebSocket handlers), so no
locks are needed; a restart simply ends the rooms. Members get messages through a small
queue each – a slow phone loses old state updates rather than holding up the TV.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

Message = dict[str, Any]
Kind = Literal["remote", "party"]
Role = Literal["tv", "phone", "host", "guest"]

CODE_TTL_S = 600
QUEUE_SIZE = 64
MAX_ROOMS = 500
# Per account, so one account can't use up all rooms.
MAX_PER_OWNER = 20


@dataclass(eq=False)
class Member:
    user_id: int
    username: str
    role: Role
    queue: asyncio.Queue[Message] = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    id: str = field(default_factory=lambda: secrets.token_hex(4))

    def send(self, message: Message) -> None:
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
        self.queue.put_nowait(message)


@dataclass(eq=False)
class Room:
    kind: Kind
    owner_id: int
    id: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    members: list[Member] = field(default_factory=list)
    code: str | None = None
    code_expires: float = 0.0
    # The last state the TV (or the host) reported – new members start from it.
    state: Message | None = None
    # Watching together: which video, with what the owner may see.
    video_id: int | None = None
    created: float = field(default_factory=time.monotonic)
    # Since when nobody is in it (a party room waits a while for a reload).
    idle_since: float | None = None

    def with_role(self, *roles: Role) -> list[Member]:
        return [m for m in self.members if m.role in roles]


class RoomError(Exception):
    pass


class Rooms:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._codes: dict[str, str] = {}
        # Rejoin tokens: a paired phone comes back after a reload without a new code.
        self._tokens: dict[str, tuple[str, int]] = {}

    def prune(self, max_age_s: float = 600) -> None:
        """Rooms nobody joined (a party link never opened) don't stay forever."""
        now = time.monotonic()
        for room in [r for r in self._rooms.values() if not r.members]:
            if now - (room.idle_since or room.created) > max_age_s:
                self.close(room)

    def create(self, kind: Kind, owner_id: int, video_id: int | None = None) -> Room:
        self.prune()
        own = [r for r in self._rooms.values() if r.owner_id == owner_id]
        if len(own) >= MAX_PER_OWNER:
            empty = [r for r in own if not r.members]
            if not empty:
                raise RoomError("Du hast schon zu viele Räume offen.")
            self.close(min(empty, key=lambda r: r.created))  # the oldest unused one goes
        if len(self._rooms) >= MAX_ROOMS:
            raise RoomError("Gerade sind zu viele Räume offen.")
        room = Room(kind=kind, owner_id=owner_id, video_id=video_id)
        self._rooms[room.id] = room
        return room

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def new_code(self, room: Room) -> str:
        """A fresh six-digit pairing code; the old one stops working."""
        if room.code:
            self._codes.pop(room.code, None)
        while True:
            code = f"{secrets.randbelow(1_000_000):06d}"
            if code not in self._codes:
                break
        self._codes[code] = room.id
        room.code = code
        room.code_expires = time.monotonic() + CODE_TTL_S
        return code

    def by_code(self, code: str) -> Room | None:
        room_id = self._codes.get(code)
        room = self._rooms.get(room_id) if room_id else None
        if room is None or time.monotonic() > room.code_expires:
            return None
        return room

    def issue_token(self, room: Room, user_id: int) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = (room.id, user_id)
        return token

    def by_token(self, token: str, user_id: int) -> Room | None:
        """Only for the account it was issued to, and only while the room exists."""
        found = self._tokens.get(token)
        if found is None or found[1] != user_id:
            return None
        return self._rooms.get(found[0])

    def drop_tokens(self, room: Room) -> None:
        for token in [t for t, (room_id, _) in self._tokens.items() if room_id == room.id]:
            del self._tokens[token]

    def join(self, room: Room, member: Member) -> None:
        room.members.append(member)
        room.idle_since = None

    def leave(self, room: Room, member: Member) -> None:
        if member in room.members:
            room.members.remove(member)
        if room.members:
            return
        if room.kind == "remote":
            self.close(room)
        else:
            # Watching together survives a reload; prune() ends it after a while.
            room.idle_since = time.monotonic()

    def close(self, room: Room) -> None:
        self._rooms.pop(room.id, None)
        if room.code:
            self._codes.pop(room.code, None)
        self.drop_tokens(room)

    def broadcast(
        self,
        room: Room,
        message: Message,
        *,
        roles: tuple[Role, ...] = (),
        exclude: Member | None = None,
    ) -> None:
        for member in list(room.members):
            if member is not exclude and (not roles or member.role in roles):
                member.send(message)

    def presence(self, room: Room) -> list[Message]:
        return [
            {"id": m.id, "user_id": m.user_id, "name": m.username, "role": m.role}
            for m in room.members
        ]

    @property
    def count(self) -> int:
        return len(self._rooms)
