"""Short-lived signed links, so a TV (Chromecast, AirPlay, …) can fetch one video.

The TV has no login cookie. The link names the user, the video and an expiry, signed
with a secret that TubeVault creates once and keeps in its database.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from sqlalchemy.orm import Session

from app.models import Setting

# Name of the settings row holding the secret (not the secret itself).
SETTING_KEY = "cast_signing_key"
LIFETIME_S = 12 * 3600  # a long film, with pauses


def _secret(db: Session) -> bytes:
    row = db.get(Setting, SETTING_KEY)
    if row is None or not isinstance(row.value, str):
        value = secrets.token_hex(32)
        if row is None:
            db.add(Setting(key=SETTING_KEY, value=value))
        else:
            row.value = value
        db.commit()
        return bytes.fromhex(value)
    return bytes.fromhex(row.value)


def _signature(secret: bytes, user_id: int, video_id: int, expires: int) -> str:
    message = f"{user_id}:{video_id}:{expires}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]


def sign(db: Session, user_id: int, video_id: int, now: float | None = None) -> tuple[int, str]:
    expires = int((now or time.time()) + LIFETIME_S)
    return expires, _signature(_secret(db), user_id, video_id, expires)


def verify(
    db: Session, user_id: int, video_id: int, expires: int, signature: str, now: float | None = None
) -> bool:
    if expires < (now or time.time()):
        return False
    expected = _signature(_secret(db), user_id, video_id, expires)
    return hmac.compare_digest(expected, signature)
