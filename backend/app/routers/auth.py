"""Login, logout, first-run setup and the current user's account."""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.deps import (
    AppConfig,
    Context,
    CurrentUser,
    DbSession,
    SessionUser,
    get_optional_user,
)
from app.core.security import (
    SESSION_COOKIE,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from app.models import ApiToken, UserSession
from app.schemas.auth import (
    AuthStatus,
    Credentials,
    PasswordChange,
    Preferences,
    SetupRequest,
    TokenCreate,
    TokenCreated,
    TokenOut,
    UserOut,
)
from app.services import auth as auth_service
from app.services.tokens import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

_setup_lock = threading.Lock()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/status")
def auth_status(request: Request, db: DbSession, settings: AppConfig) -> AuthStatus:
    user = get_optional_user(request, db, settings)
    return AuthStatus(
        setup_required=auth_service.user_count(db) == 0,
        user=UserOut.model_validate(user) if user else None,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(
    body: SetupRequest, request: Request, response: Response, db: DbSession, settings: AppConfig
) -> UserOut:
    with _setup_lock:
        if auth_service.user_count(db) > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Die Einrichtung ist bereits abgeschlossen."
            )
        user = auth_service.create_user(db, body.username, body.password, is_admin=True)
    token = auth_service.create_session(
        db, user, request.headers.get("user-agent"), settings.session_days
    )
    auth_service.set_session_cookie(response, request, token, settings)
    return UserOut.model_validate(user)


@router.post("/login")
def login(
    body: Credentials,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> UserOut:
    throttle = ctx.login_throttle
    key = _client_key(request)
    if throttle.is_blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zu viele fehlgeschlagene Anmeldungen. Bitte in einigen Minuten erneut versuchen.",
        )
    user = auth_service.find_user(db, body.username)
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzername oder Passwort ist falsch.")
    throttle.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    token = auth_service.create_session(
        db, user, request.headers.get("user-agent"), settings.session_days
    )
    auth_service.set_session_cookie(response, request, token, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession, settings: AppConfig) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session = db.get(UserSession, hash_token(token))
        if session is not None:
            db.delete(session)
            db.commit()
    auth_service.clear_session_cookie(response, settings)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.put("/me/preferences")
def update_preferences(body: Preferences, user: CurrentUser, db: DbSession) -> UserOut:
    user.preferences = {**(user.preferences or {}), **body.model_dump(exclude_none=True)}
    db.commit()
    return UserOut.model_validate(user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange, request: Request, user: SessionUser, db: DbSession
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das aktuelle Passwort ist falsch.")
    user.password_hash = hash_password(body.new_password)
    # Sign out every other device.
    current = request.cookies.get(SESSION_COOKIE)
    current_id = hash_token(current) if current else None
    for session in list(user.sessions):
        if session.id != current_id:
            db.delete(session)
    db.commit()


# --- API tokens -------------------------------------------------------------------------


@router.get("/tokens")
def list_tokens(user: SessionUser, db: DbSession) -> list[TokenOut]:
    tokens = db.query(ApiToken).filter_by(user_id=user.id).order_by(ApiToken.created_at.desc())
    return [TokenOut.model_validate(t) for t in tokens]


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
def new_token(body: TokenCreate, user: SessionUser, db: DbSession) -> TokenCreated:
    token, raw = create_token(db, user, body.name, body.scope, body.expires_days)
    created = TokenOut.model_validate(token).model_dump()
    return TokenCreated.model_validate({**created, "token": raw})


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_token(token_id: int, user: SessionUser, db: DbSession) -> None:
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token nicht gefunden")
    db.delete(token)
    db.commit()
