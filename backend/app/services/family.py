"""Family devices: one browser (the TV, the tablet in the kitchen) where profiles switch
with a tap – "Wer schaut?" – instead of typing passwords.

An admin sets a device up once; it gets a long-lived cookie, of which only a hash is
kept. On that device every account that agreed to appear can be chosen, behind its PIN
if it has one. Admins and accounts with two-factor login always need a PIN there.
Wrong PINs are slowed down per account.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import hash_password, hash_token, verify_password
from app.models import FamilyDevice, User
from app.services.auth import LoginThrottle, cookie_path

FAMILY_COOKIE = "tubevault_family"
# Browsers keep cookies for at most 400 days; using the device renews it.
COOKIE_DAYS = 400
_PIN = re.compile(r"\d{4,8}")


class PinThrottle(LoginThrottle):
    """Five wrong PINs per account, then a 15-minute pause."""

    def __init__(self) -> None:
        super().__init__(max_failures=5, window_seconds=900)


def valid_pin(pin: str) -> bool:
    return bool(_PIN.fullmatch(pin))


def set_pin(user: User, pin: str | None) -> None:
    user.pin_hash = hash_password(pin) if pin else None


def check_pin(user: User, pin: str | None) -> bool:
    if not user.pin_hash:
        return True
    return bool(pin) and verify_password(user.pin_hash, pin or "")


def can_appear(user: User) -> bool:
    return user.on_family_devices and (user.has_pin or not user.needs_pin)


def profiles(db: Session) -> list[User]:
    users = db.scalars(select(User).where(User.on_family_devices.is_(True)))
    return sorted((u for u in users if can_appear(u)), key=lambda u: u.username.lower())


def create_device(db: Session, name: str, created_by: User) -> tuple[FamilyDevice, str]:
    token = secrets.token_urlsafe(32)
    device = FamilyDevice(
        token_hash=hash_token(token), name=name.strip(), created_by_id=created_by.id
    )
    db.add(device)
    db.commit()
    return device, token


def device_from_request(request: Request, db: Session) -> FamilyDevice | None:
    token = request.cookies.get(FAMILY_COOKIE)
    if not token or len(token) > 128:
        return None
    return db.scalar(select(FamilyDevice).where(FamilyDevice.token_hash == hash_token(token)))


def touch(db: Session, device: FamilyDevice) -> None:
    now = datetime.now(UTC)
    last = device.last_used_at
    if last is None or now - last.replace(tzinfo=UTC) > timedelta(hours=1):
        device.last_used_at = now
        db.commit()


def set_device_cookie(response: Response, request: Request, token: str, settings: Settings) -> None:
    response.set_cookie(
        FAMILY_COOKIE,
        token,
        max_age=COOKIE_DAYS * 86400,
        path=cookie_path(settings),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def clear_device_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(FAMILY_COOKIE, path=cookie_path(settings), httponly=True, samesite="lax")


class FamilySettingsError(ValueError):
    pass


def apply_settings(user: User, on_family_devices: bool | None, pin: str | None) -> None:
    """Applies a partial change, refusing a combination that would open an account."""
    if pin is not None and pin != "" and not valid_pin(pin):
        raise FamilySettingsError("Die PIN besteht aus 4 bis 8 Ziffern.")
    show = user.on_family_devices if on_family_devices is None else on_family_devices
    has_pin = user.has_pin if pin is None else pin != ""
    if show and user.needs_pin and not has_pin:
        raise FamilySettingsError(
            "Admins und Konten mit Zwei-Faktor-Anmeldung brauchen auf Familiengeräten eine PIN."
        )
    if pin is not None:
        set_pin(user, pin or None)
    user.on_family_devices = show
