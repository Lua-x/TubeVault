"""Login through an OpenID Connect provider: Authelia, Authentik, Keycloak, Pocket ID, …

Authorization code flow with PKCE. The ID token comes straight from the provider's
token endpoint over TLS, so – as OpenID Connect Core 3.1.3.7 allows – its issuer is
trusted through TLS instead of a signature check; audience, expiry and nonce are
checked. That keeps TubeVault free of a JWT/crypto dependency.

Nothing here runs unless OIDC_ISSUER, OIDC_CLIENT_ID and OIDC_CLIENT_SECRET are set.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User

HTTP_TIMEOUT = 10
DISCOVERY_TTL = 3600.0
PENDING_TTL = 600.0
CLOCK_LEEWAY = 60
POST_AUTH = "client_secret_post"
USERNAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class OidcError(Exception):
    """Shown to the user on the login page (German)."""

    back_to = "/login"  # where to show it: the settings page while linking an account


def http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", **(headers or {})})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 – configured provider
            data = json.load(response)
    except (OSError, ValueError) as exc:
        raise OidcError(f"Der Anmeldedienst ist nicht erreichbar: {exc}") from exc
    if not isinstance(data, dict):
        raise OidcError("Der Anmeldedienst hat unerwartet geantwortet.")
    return data


def http_post_form(url: str, form: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode()
    request = urllib.request.Request(  # noqa: S310 – configured provider
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise OidcError(f"Der Anmeldedienst lehnt ab ({exc.code}): {detail}") from exc
    except (OSError, ValueError) as exc:
        raise OidcError(f"Der Anmeldedienst ist nicht erreichbar: {exc}") from exc
    if not isinstance(data, dict):
        raise OidcError("Der Anmeldedienst hat unerwartet geantwortet.")
    return data


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as exc:
        raise OidcError("Das ID-Token des Anmeldedienstes ist unlesbar.") from exc
    if not isinstance(data, dict):
        raise OidcError("Das ID-Token des Anmeldedienstes ist unlesbar.")
    return data


@dataclass(frozen=True, slots=True)
class Provider:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None


@dataclass(slots=True)
class Pending:
    nonce: str
    verifier: str
    next_path: str
    link_user_id: int | None
    created: float


@dataclass(slots=True)
class LoginResult:
    claims: dict[str, Any]
    next_path: str
    link_user_id: int | None


def safe_next(value: str | None) -> str:
    """Only paths inside TubeVault – never an open redirect."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


class OidcClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider: Provider | None = None
        self._provider_at = 0.0
        self._pending: dict[str, Pending] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._settings.oidc_enabled

    def provider(self) -> Provider:
        now = time.monotonic()
        if self._provider and now - self._provider_at < DISCOVERY_TTL:
            return self._provider
        issuer = (self._settings.oidc_issuer or "").rstrip("/")
        data = http_get_json(f"{issuer}/.well-known/openid-configuration")
        try:
            provider = Provider(
                issuer=str(data["issuer"]),
                authorization_endpoint=str(data["authorization_endpoint"]),
                token_endpoint=str(data["token_endpoint"]),
                userinfo_endpoint=str(data["userinfo_endpoint"])
                if data.get("userinfo_endpoint")
                else None,
            )
        except KeyError as exc:
            raise OidcError(
                f"Die Konfiguration des Anmeldedienstes ist unvollständig: {exc}"
            ) from exc
        self._provider, self._provider_at = provider, now
        return provider

    def start(self, redirect_uri: str, next_path: str, link_user_id: int | None = None) -> str:
        """The URL that sends the browser to the provider."""
        provider = self.provider()
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        now = time.monotonic()
        with self._lock:
            self._pending = {
                k: p for k, p in self._pending.items() if now - p.created < PENDING_TTL
            }
            self._pending[state] = Pending(nonce, verifier, safe_next(next_path), link_user_id, now)
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.oidc_client_id,
                "redirect_uri": redirect_uri,
                "scope": self._settings.oidc_scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in provider.authorization_endpoint else "?"
        return f"{provider.authorization_endpoint}{separator}{query}"

    def finish(self, code: str, state: str, redirect_uri: str) -> LoginResult:
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or time.monotonic() - pending.created > PENDING_TTL:
            raise OidcError("Die Anmeldung ist abgelaufen. Bitte noch einmal versuchen.")
        try:
            return self._exchange(code, redirect_uri, pending)
        except OidcError as exc:
            if pending.link_user_id is not None:
                exc.back_to = "/settings"
            raise

    def _exchange(self, code: str, redirect_uri: str, pending: Pending) -> LoginResult:
        provider = self.provider()
        settings = self._settings
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": pending.verifier,
        }
        headers: dict[str, str] = {}
        client_id, secret = settings.oidc_client_id or "", settings.oidc_client_secret or ""
        if settings.oidc_token_auth == POST_AUTH:
            form |= {"client_id": client_id, "client_secret": secret}
        else:
            pair = f"{urllib.parse.quote(client_id)}:{urllib.parse.quote(secret)}"
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
        tokens = http_post_form(provider.token_endpoint, form, headers)
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("Der Anmeldedienst hat kein ID-Token geschickt.")
        claims = self._validated(decode_jwt_payload(id_token), provider, pending.nonce)

        access_token = tokens.get("access_token")
        if provider.userinfo_endpoint and isinstance(access_token, str):
            try:
                info = http_get_json(
                    provider.userinfo_endpoint, {"Authorization": f"Bearer {access_token}"}
                )
            except OidcError:
                info = {}
            if info.get("sub") == claims["sub"]:
                claims = {**info, **claims}  # groups etc. often only come from userinfo
        return LoginResult(claims, pending.next_path, pending.link_user_id)

    def _validated(self, claims: dict[str, Any], provider: Provider, nonce: str) -> dict[str, Any]:
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if claims.get("iss") != provider.issuer:
            raise OidcError("Das ID-Token stammt von einem anderen Aussteller.")
        if self._settings.oidc_client_id not in audiences:
            raise OidcError("Das ID-Token ist für eine andere Anwendung ausgestellt.")
        expires = claims.get("exp")
        if not isinstance(expires, (int, float)) or expires < time.time() - CLOCK_LEEWAY:
            raise OidcError(
                "Das ID-Token ist abgelaufen. Uhrzeit von Server und Anmeldedienst prüfen."
            )
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OidcError(
                "Die Anmeldung passt nicht zu dieser Sitzung. Bitte noch einmal versuchen."
            )
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise OidcError("Das ID-Token enthält keine Benutzerkennung.")
        return claims


def _groups(claims: dict[str, Any], claim: str) -> list[str]:
    value = claims.get(claim)
    if isinstance(value, str):
        return [value]
    return [str(group) for group in value] if isinstance(value, list) else []


def _unique_username(db: Session, wanted: str) -> str:
    base = USERNAME_CHARS.sub("", wanted)[:60].strip("._-") or "benutzer"
    if len(base) < 2:
        base = f"{base}-user"
    name, number = base, 1
    while db.scalar(select(User.id).where(func.lower(User.username) == name.lower())):
        number += 1
        name = f"{base}-{number}"
    return name


def account_for(db: Session, claims: dict[str, Any], settings: Settings) -> User:
    """The TubeVault user for a provider account – found, or created if allowed."""
    subject = str(claims["sub"])
    admin_by_group: bool | None = None
    if settings.oidc_admin_group:
        admin_by_group = settings.oidc_admin_group in _groups(claims, settings.oidc_groups_claim)

    user = db.scalar(select(User).where(User.oidc_subject == subject))
    if user is not None:
        if admin_by_group is True:
            user.is_admin = True
        elif admin_by_group is False and user.is_admin:
            admins = db.scalar(select(func.count()).where(User.is_admin.is_(True))) or 0
            if admins > 1:  # never take away the last admin
                user.is_admin = False
        db.commit()
        return user

    if not settings.oidc_auto_create:
        raise OidcError(
            "Für dieses Konto gibt es in TubeVault noch keinen Benutzer. Ein Admin kann ihn "
            "anlegen – danach in den Einstellungen mit dem Anmeldedienst verbinden."
        )
    first = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    wanted = str(
        claims.get(settings.oidc_username_claim)
        or claims.get("preferred_username")
        or str(claims.get("email") or "").split("@")[0]
        or "benutzer"
    )
    user = User(
        username=_unique_username(db, wanted),
        password_hash="",  # no password: this account logs in through the provider
        is_admin=first or bool(admin_by_group),
        oidc_subject=subject,
    )
    db.add(user)
    db.commit()
    return user


def link(db: Session, user: User, claims: dict[str, Any]) -> None:
    subject = str(claims["sub"])
    other = db.scalar(select(User).where(User.oidc_subject == subject, User.id != user.id))
    if other is not None:
        raise OidcError(f"Dieses Konto ist schon mit dem Benutzer „{other.username}“ verbunden.")
    user.oidc_subject = subject
    db.commit()
