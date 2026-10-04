"""Family devices and "Wer schaut?" – switching profiles with a tap (app/services/family.py)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core.deps import AppConfig, Context, DbSession, SessionUser
from app.core.security import SESSION_COOKIE, hash_token
from app.models import FamilyDevice, User, UserSession
from app.schemas.auth import UserOut
from app.services import auth as auth_service
from app.services import family

router = APIRouter(prefix="/family", tags=["family"])


class FamilyProfile(BaseModel):
    id: int
    username: str
    has_pin: bool
    restricted: bool


class SwitchRequest(BaseModel):
    user_id: int
    pin: str | None = Field(default=None, max_length=8)


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class DeviceOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None
    # The browser asking is this device.
    current: bool


def family_device(request: Request, db: DbSession) -> FamilyDevice:
    device = family.device_from_request(request, db)
    if device is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dieses Gerät ist kein Familiengerät.")
    return device


Device = Annotated[FamilyDevice, Depends(family_device)]


def _admin(user: User) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Admins")
    return user


@router.get("/profiles")
def list_profiles(device: Device, db: DbSession) -> list[FamilyProfile]:
    family.touch(db, device)
    return [
        FamilyProfile(id=u.id, username=u.username, has_pin=u.has_pin, restricted=u.restricted)
        for u in family.profiles(db)
    ]


@router.post("/switch")
def switch_profile(
    body: SwitchRequest,
    request: Request,
    response: Response,
    device: Device,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> UserOut:
    user = db.get(User, body.user_id)
    if user is None or not family.can_appear(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil nicht gefunden")
    key = f"pin:{user.id}"
    if ctx.pin_throttle.is_blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zu oft die falsche PIN. Bitte in einer Viertelstunde erneut versuchen.",
        )
    if not family.check_pin(user, body.pin):
        ctx.pin_throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falsche PIN.")
    ctx.pin_throttle.reset(key)
    # The profile that watched before is signed out on this device.
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        db.execute(delete(UserSession).where(UserSession.id == hash_token(old)))
    token = auth_service.create_session(
        db, user, request.headers.get("user-agent"), settings.session_days
    )
    auth_service.set_session_cookie(response, request, token, settings)
    family.touch(db, device)
    return UserOut.model_validate(user)


def _out(device: FamilyDevice, current: FamilyDevice | None) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        created_at=device.created_at,
        last_used_at=device.last_used_at,
        current=current is not None and current.id == device.id,
    )


@router.get("/devices")
def list_devices(request: Request, user: SessionUser, db: DbSession) -> list[DeviceOut]:
    _admin(user)
    current = family.device_from_request(request, db)
    devices = db.scalars(select(FamilyDevice).order_by(FamilyDevice.created_at))
    return [_out(d, current) for d in devices]


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(
    body: DeviceIn,
    request: Request,
    response: Response,
    user: SessionUser,
    db: DbSession,
    settings: AppConfig,
) -> DeviceOut:
    """Makes the browser asking a family device."""
    _admin(user)
    previous = family.device_from_request(request, db)
    if previous is not None:
        db.delete(previous)
    device, token = family.create_device(db, body.name, user)
    family.set_device_cookie(response, request, token, settings)
    return _out(device, device)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(
    device_id: int,
    request: Request,
    response: Response,
    user: SessionUser,
    db: DbSession,
    settings: AppConfig,
) -> None:
    _admin(user)
    device = db.get(FamilyDevice, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gerät nicht gefunden")
    current = family.device_from_request(request, db)
    if current is not None and current.id == device.id:
        family.clear_device_cookie(response, settings)
    db.delete(device)
    db.commit()
