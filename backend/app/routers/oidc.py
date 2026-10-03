"""Login through an OpenID Connect provider (see app/services/oidc.py)."""

from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.core.deps import AppConfig, Context, DbSession, SessionUser
from app.core.urls import public_base
from app.models import User
from app.services import auth as auth_service
from app.services import oidc

router = APIRouter(prefix="/auth/oidc", tags=["auth"])
log = logging.getLogger(__name__)


def redirect_uri(request: Request, settings: Settings) -> str:
    """Where the provider sends the browser back – also shown in the admin page."""
    return f"{public_base(request, settings)}/api/auth/oidc/callback"


def _app_redirect(settings: Settings, path: str, **query: str) -> RedirectResponse:
    target = f"{settings.base_path}{oidc.safe_next(path)}"
    if query:
        target += ("&" if "?" in target else "?") + urllib.parse.urlencode(query)
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


def _require_enabled(ctx: Context) -> oidc.OidcClient:
    if not ctx.oidc.enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Anmeldung über OIDC ist nicht eingerichtet."
        )
    return ctx.oidc


@router.get("/login")
def oidc_login(
    request: Request, ctx: Context, settings: AppConfig, next: str = "/"
) -> RedirectResponse:
    client = _require_enabled(ctx)
    try:
        url = client.start(redirect_uri(request, settings), next)
    except oidc.OidcError as exc:
        return _app_redirect(settings, "/login", oidc_error=str(exc))
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/link")
def oidc_link(
    request: Request, user: SessionUser, ctx: Context, settings: AppConfig
) -> RedirectResponse:
    """Connect the signed-in account – the only way to link an existing user."""
    client = _require_enabled(ctx)
    try:
        url = client.start(redirect_uri(request, settings), "/settings", link_user_id=user.id)
    except oidc.OidcError as exc:
        return _app_redirect(settings, "/settings", oidc_error=str(exc))
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/callback")
def oidc_callback(
    request: Request,
    db: DbSession,
    ctx: Context,
    settings: AppConfig,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    client = _require_enabled(ctx)
    if error or not code or not state:
        message = error_description or error or "Die Anmeldung wurde abgebrochen."
        return _app_redirect(settings, "/login", oidc_error=message)
    try:
        result = client.finish(code, state, redirect_uri(request, settings))
        if result.link_user_id is not None:
            linking = db.get(User, result.link_user_id)
            try:
                if linking is None:
                    raise oidc.OidcError("Der Benutzer existiert nicht mehr.")
                oidc.link(db, linking, result.claims)
            except oidc.OidcError as exc:
                exc.back_to = "/settings"
                raise
            log.info("Benutzer %s mit dem Anmeldedienst verbunden", linking.username)
            return _app_redirect(settings, "/settings", oidc="linked")
        user = oidc.account_for(db, result.claims, settings)
    except oidc.OidcError as exc:
        log.warning("OIDC-Anmeldung fehlgeschlagen: %s", exc)
        return _app_redirect(settings, exc.back_to, oidc_error=str(exc))
    token = auth_service.create_session(
        db, user, request.headers.get("user-agent"), settings.session_days
    )
    response = _app_redirect(settings, result.next_path)
    auth_service.set_session_cookie(response, request, token, settings)
    log.info("Anmeldung über den Anmeldedienst: %s", user.username)
    return response


@router.post("/unlink", status_code=status.HTTP_204_NO_CONTENT)
def oidc_unlink(user: SessionUser, db: DbSession) -> None:
    if not user.has_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Erst ein Passwort festlegen – sonst kommst du nicht mehr in dein Konto.",
        )
    user.oidc_subject = None
    db.commit()
