from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, ForeignKey, Index, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.video import Video


# Channels a restricted user may see.
user_channels = Table(
    "user_channels",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("channel_id", ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None]
    # Two-factor login with an authenticator app. The secret exists from setup on;
    # it only counts once enabled. last counter: each code works only once.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled_at: Mapped[datetime | None]
    totp_last_counter: Mapped[int | None]
    recovery_codes: Mapped[list[str]] = mapped_column(default=list)  # SHA-256 hashes
    # What the user may see and do. Admins always see everything.
    channel_access: Mapped[str] = mapped_column(String(16), default="all")  # all | selected
    may_add: Mapped[bool] = mapped_column(default=True)  # add videos, subscribe, downloads
    channels: Mapped[list[Channel]] = relationship(secondary=user_channels)
    # Linked account at the OpenID Connect provider ("sub" claim).
    oidc_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    added_videos: Mapped[list[Video]] = relationship(back_populates="added_by")

    @property
    def restricted(self) -> bool:
        """Only sees the channels chosen for it (e.g. a kids profile)."""
        return not self.is_admin and self.channel_access == "selected"

    @property
    def channel_ids(self) -> list[int]:
        return sorted(channel.id for channel in self.channels)

    @property
    def can_add(self) -> bool:
        return self.is_admin or (self.may_add and not self.restricted)

    @property
    def has_password(self) -> bool:
        """Accounts created through the provider have none until one is set."""
        return bool(self.password_hash)

    @property
    def oidc_linked(self) -> bool:
        return self.oidc_subject is not None

    @property
    def two_factor(self) -> bool:
        return self.totp_enabled_at is not None and bool(self.totp_secret)


# Usernames are unique regardless of case.
Index("ix_users_username_lower", func.lower(User.username), unique=True)


class UserSession(Base):
    """A login session. Only the SHA-256 hash of the cookie token is stored."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="sessions")


class ApiToken(Base):
    """Personal access token for scripts and shortcuts. Only its SHA-256 hash is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # First characters of the token, shown so people can tell their tokens apart.
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # "read": GET only; "full": everything the user may do (except managing tokens).
    scope: Mapped[str] = mapped_column(String(16), default="read")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]

    user: Mapped[User] = relationship()
