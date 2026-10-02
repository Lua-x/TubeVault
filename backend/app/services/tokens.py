"""Personal API tokens (`Authorization: Bearer tv_…`)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import ApiToken, User

TOKEN_PREFIX = "tv_"  # noqa: S105 – a marker, not a secret
TOUCH_INTERVAL = timedelta(minutes=5)
Scope = Literal["read", "full"]


def create_token(
    db: Session, user: User, name: str, scope: Scope, expires_days: int | None
) -> tuple[ApiToken, str]:
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user.id,
        name=name,
        prefix=raw[:11],
        token_hash=hash_token(raw),
        scope=scope,
        expires_at=datetime.now(UTC) + timedelta(days=expires_days) if expires_days else None,
    )
    db.add(token)
    db.commit()
    return token, raw


def verify_token(db: Session, raw: str) -> ApiToken | None:
    if not raw.startswith(TOKEN_PREFIX):
        return None
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    now = datetime.now(UTC)
    if token is None or (token.expires_at is not None and token.expires_at <= now):
        return None
    if token.last_used_at is None or now - token.last_used_at > TOUCH_INTERVAL:
        token.last_used_at = now
        db.commit()
    return token
