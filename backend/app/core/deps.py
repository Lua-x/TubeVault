"""FastAPI dependencies: database session, current user, settings."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.config import Settings
from app.core.context import AppContext
from app.core.security import SESSION_COOKIE, hash_token
from app.models import User, UserSession
from app.services.access import require_youtube

# Refresh `last_seen_at` (and slide the expiry) at most this often.
SESSION_TOUCH_INTERVAL = timedelta(minutes=10)


def get_context(conn: HTTPConnection) -> AppContext:
    ctx: AppContext = conn.app.state.ctx
    return ctx


def get_settings(ctx: Annotated[AppContext, Depends(get_context)]) -> Settings:
    return ctx.settings


def get_db(ctx: Annotated[AppContext, Depends(get_context)]) -> Iterator[Session]:
    with ctx.sessions() as db:
        yield db


def user_from_token(db: Session, token: str | None, settings: Settings) -> User | None:
    if not token:
        return None
    session = db.get(UserSession, hash_token(token))
    now = datetime.now(UTC)
    if session is None:
        return None
    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return None
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        session.expires_at = now + timedelta(days=settings.session_days)
        db.commit()
    return session.user


READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        # An API token replaces the cookie completely, never falls back to it.
        from app.services.tokens import verify_token

        token = verify_token(db, authorization[7:].strip())
        if token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiges oder abgelaufenes Token")
        if token.scope != "full" and request.method not in READ_ONLY_METHODS:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Dieses Token darf nur lesen")
        request.state.api_token = token
        return token.user
    return user_from_token(db, request.cookies.get(SESSION_COOKIE), settings)


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    return user


def require_session(request: Request, user: Annotated[User, Depends(get_current_user)]) -> User:
    """Account actions (tokens, password) need a real login, not an API token."""
    if getattr(request.state, "api_token", None) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur nach Anmeldung im Browser möglich")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Administratoren")
    return user


def websocket_user(websocket: WebSocket, db: Session, settings: Settings) -> User | None:
    return user_from_token(db, websocket.cookies.get(SESSION_COOKIE), settings)


DbSession = Annotated[Session, Depends(get_db)]


def require_can_add(user: Annotated[User, Depends(get_current_user)], db: DbSession) -> User:
    """Adding videos, subscriptions and the download queue (not for view-only accounts)."""
    if not user.can_add:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Dein Konto darf keine Videos hinzufügen oder abonnieren."
        )
    require_youtube(db)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionUser = Annotated[User, Depends(require_session)]
AdminUser = Annotated[User, Depends(require_admin)]
Context = Annotated[AppContext, Depends(get_context)]
AppConfig = Annotated[Settings, Depends(get_settings)]
