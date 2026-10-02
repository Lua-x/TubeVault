"""Sessions, login throttling and the initial admin account."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import SESSION_COOKIE, hash_password, hash_token, new_session_token
from app.models import User, UserSession

log = logging.getLogger(__name__)


def user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))


def create_user(db: Session, username: str, password: str, *, is_admin: bool) -> User:
    user = User(username=username.strip(), password_hash=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


def create_session(db: Session, user: User, user_agent: str | None, days: int) -> str:
    token = new_session_token()
    now = datetime.now(UTC)
    db.add(
        UserSession(
            id=hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=days),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    user.last_login_at = now
    db.commit()
    return token


def cookie_path(settings: Settings) -> str:
    return settings.base_path or "/"


def set_session_cookie(
    response: Response, request: Request, token: str, settings: Settings
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        path=cookie_path(settings),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path=cookie_path(settings), httponly=True, samesite="lax"
    )


def purge_expired_sessions(db: Session) -> int:
    result = db.execute(delete(UserSession).where(UserSession.expires_at <= datetime.now(UTC)))
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def bootstrap_admin(db: Session, settings: Settings) -> None:
    """Create the admin from ADMIN_USER/ADMIN_PASSWORD when the database has no users yet."""
    if user_count(db) > 0:
        return
    if settings.admin_user and settings.admin_password:
        if len(settings.admin_password) < 8:
            log.error("ADMIN_PASSWORD ist kürzer als 8 Zeichen – Admin wird nicht angelegt.")
            return
        create_user(db, settings.admin_user, settings.admin_password, is_admin=True)
        log.info("Admin-Konto '%s' aus den Umgebungsvariablen angelegt", settings.admin_user)
    else:
        log.info("Noch kein Benutzer vorhanden – Einrichtung im Browser öffnen.")


class LoginThrottle:
    """Blocks a client after too many failed logins within a time window."""

    def __init__(self, max_failures: int = 10, window_seconds: float = 600) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] > self._window:
            attempts.popleft()
        return attempts

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self._max

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
