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
from app.models import ApiToken, User, UserSession
from app.schemas.auth import (
    AuthStatus,
    Credentials,
    PasswordChange,
    Preferences,
    RecoveryCodes,
    SetupRequest,
    TokenCreate,
    TokenCreated,
    TokenOut,
    TwoFactorChallenge,
    TwoFactorCode,
    TwoFactorLogin,
    TwoFactorSetup,
    TwoFactorStatus,
    UserOut,
)
from app.services import auth as auth_service
from app.services import two_factor
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
) -> UserOut | TwoFactorChallenge:
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
        db.commit()
    if user.two_factor:
        return TwoFactorChallenge(ticket=ctx.login_tickets.issue(user.id))
    return _start_session(db, user, request, response, settings)


def _start_session(
    db: DbSession, user: User, request: Request, response: Response, settings: AppConfig
) -> UserOut:
    token = auth_service.create_session(
        db, user, request.headers.get("user-agent"), settings.session_days
    )
    auth_service.set_session_cookie(response, request, token, settings)
    return UserOut.model_validate(user)


@router.post("/login/2fa")
def login_two_factor(
    body: TwoFactorLogin,
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
    user_id = ctx.login_tickets.user_for(body.ticket)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Die Anmeldung ist abgelaufen. Bitte neu anmelden."
        )
    if not two_factor.check_code(db, user, body.code):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Der Code stimmt nicht.")
    throttle.reset(key)
    ctx.login_tickets.consume(body.ticket)
    return _start_session(db, user, request, response, settings)


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
    _sign_out_others(request, db, user)  # every other device


# --- two-factor login ------------------------------------------------------------------


def _sign_out_others(request: Request, db: DbSession, user: User) -> None:
    current = request.cookies.get(SESSION_COOKIE)
    current_id = hash_token(current) if current else None
    for session in list(user.sessions):
        if session.id != current_id:
            db.delete(session)
    db.commit()


def _two_factor_error(exc: two_factor.TwoFactorError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/2fa")
def two_factor_status(user: SessionUser) -> TwoFactorStatus:
    return TwoFactorStatus(
        enabled=user.two_factor,
        recovery_codes_left=len(user.recovery_codes or []) if user.two_factor else 0,
    )


@router.post("/2fa/setup")
def two_factor_setup(user: SessionUser, db: DbSession) -> TwoFactorSetup:
    try:
        secret, uri = two_factor.begin_setup(db, user)
    except two_factor.TwoFactorError as exc:
        raise _two_factor_error(exc) from exc
    return TwoFactorSetup(secret=secret, uri=uri)


@router.post("/2fa/enable")
def two_factor_enable(
    body: TwoFactorCode, request: Request, user: SessionUser, db: DbSession
) -> RecoveryCodes:
    try:
        codes = two_factor.enable(db, user, body.code)
    except two_factor.TwoFactorError as exc:
        raise _two_factor_error(exc) from exc
    _sign_out_others(request, db, user)  # from now on every login needs the code
    return RecoveryCodes(recovery_codes=codes)


def _require_code(db: DbSession, user: User, code: str, request: Request, ctx: Context) -> None:
    key = _client_key(request)
    if ctx.login_throttle.is_blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Zu viele falsche Codes.")
    if not two_factor.check_code(db, user, code):
        ctx.login_throttle.record_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Der Code stimmt nicht.")


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_disable(
    body: TwoFactorCode, request: Request, user: SessionUser, db: DbSession, ctx: Context
) -> None:
    _require_code(db, user, body.code, request, ctx)
    two_factor.disable(db, user)


@router.post("/2fa/recovery-codes")
def two_factor_recovery_codes(
    body: TwoFactorCode, request: Request, user: SessionUser, db: DbSession, ctx: Context
) -> RecoveryCodes:
    _require_code(db, user, body.code, request, ctx)
    return RecoveryCodes(recovery_codes=two_factor.regenerate_recovery_codes(db, user))


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
