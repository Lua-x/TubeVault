"""User management for administrators."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import AdminUser, DbSession
from app.core.security import hash_password
from app.models import Channel, User
from app.schemas.auth import NewUser, UserOut, UserUpdate
from app.services import auth as auth_service
from app.services import two_factor

router = APIRouter(prefix="/users", tags=["users"])


def _admin_count(db: DbSession) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))) or 0


@router.get("")
def list_users(_: AdminUser, db: DbSession) -> list[UserOut]:
    users = db.scalars(select(User).order_by(func.lower(User.username)))
    return [UserOut.model_validate(u) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: NewUser, _: AdminUser, db: DbSession) -> UserOut:
    if auth_service.find_user(db, body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diesen Benutzernamen gibt es schon.")
    user = auth_service.create_user(db, body.username, body.password, is_admin=body.is_admin)
    _apply_access(db, user, body.channel_access, body.may_add, body.channel_ids)
    db.commit()
    return UserOut.model_validate(user)


def _apply_access(
    db: DbSession,
    user: User,
    channel_access: str | None,
    may_add: bool | None,
    channel_ids: list[int] | None,
) -> None:
    if channel_access is not None:
        user.channel_access = channel_access
    if may_add is not None:
        user.may_add = may_add
    if channel_ids is not None:
        user.channels = list(db.scalars(select(Channel).where(Channel.id.in_(channel_ids))))


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: AdminUser, db: DbSession) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    if body.is_admin is not None and body.is_admin != user.is_admin:
        if not body.is_admin and user.is_admin and _admin_count(db) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Es muss mindestens einen Admin geben."
            )
        user.is_admin = body.is_admin
    if body.password:
        user.password_hash = hash_password(body.password)
        if user.id != admin.id:
            user.sessions.clear()
    _apply_access(db, user, body.channel_access, body.may_add, body.channel_ids)
    db.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: AdminUser, db: DbSession) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Du kannst dich nicht selbst löschen.")
    db.delete(user)
    db.commit()


@router.delete("/{user_id}/2fa", status_code=status.HTTP_204_NO_CONTENT)
def reset_two_factor(user_id: int, _: AdminUser, db: DbSession) -> None:
    """For a lost phone: the user can log in with the password and set it up again."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    two_factor.disable(db, user)
