from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ApiModel

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{2,64}$"


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class NewUser(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=1024)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class SetupRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=1024)


class UserUpdate(BaseModel):
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=1024)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class Preferences(BaseModel):
    """Partial update: only the fields that are sent are changed."""

    theme: Literal["system", "dark", "light"] | None = None
    sponsorblock_skip: bool | None = None
    autoplay_next: bool | None = None


class UserOut(ApiModel):
    id: int
    username: str
    is_admin: bool
    preferences: dict[str, Any]
    created_at: datetime
    last_login_at: datetime | None


class AuthStatus(BaseModel):
    setup_required: bool
    user: UserOut | None
