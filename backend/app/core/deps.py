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


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    return user_from_token(db, request.cookies.get(SESSION_COOKIE), settings)


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Administratoren")
    return user


def websocket_user(websocket: WebSocket, db: Session, settings: Settings) -> User | None:
    return user_from_token(db, websocket.cookies.get(SESSION_COOKIE), settings)


DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
Context = Annotated[AppContext, Depends(get_context)]
AppConfig = Annotated[Settings, Depends(get_settings)]
