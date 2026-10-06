from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.video import str_enum

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.video import Video


class SubscriptionKind(enum.StrEnum):
    CHANNEL = "channel"
    PLAYLIST = "playlist"


class ItemState(enum.StrEnum):
    QUEUED = "queued"  # a download job exists
    DOWNLOADED = "downloaded"
    FILTERED = "filtered"  # excluded by the subscription's filters
    SKIPPED = "skipped"  # older videos not taken when subscribing
    FAILED = "failed"
    REMOVED = "removed"  # deleted by cleanup or by hand – never downloaded again


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("kind", "youtube_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[SubscriptionKind] = mapped_column(str_enum(SubscriptionKind))
    youtube_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(512))
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)

    check_interval_minutes: Mapped[int] = mapped_column(default=360)
    # Instead of the interval: check on these weekdays (0 = Monday) at this local time.
    check_days: Mapped[list[int] | None] = mapped_column(JSON)
    check_time: Mapped[str | None] = mapped_column(String(5))
    last_checked_at: Mapped[datetime | None]
    next_check_at: Mapped[datetime | None] = mapped_column(index=True)
    last_check_error: Mapped[str | None] = mapped_column(Text)
    # How many existing videos the first check takes (None = all).
    backfill: Mapped[int | None] = mapped_column(default=5)

    # Filters
    include_shorts: Mapped[bool] = mapped_column(default=False)
    include_live: Mapped[bool] = mapped_column(default=False)
    min_duration_s: Mapped[int | None]
    max_duration_s: Mapped[int | None]
    date_after: Mapped[date | None]

    # Download options that override the global settings (container, max_height, …).
    download_options: Mapped[dict[str, Any]] = mapped_column(default=dict)

    # Cleanup
    keep_days: Mapped[int | None]
    keep_last: Mapped[int | None]

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    channel: Mapped[Channel | None] = relationship()
    items: Mapped[list[SubscriptionItem]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def has_cleanup(self) -> bool:
        return bool(self.keep_days or self.keep_last)


class SubscriptionItem(Base):
    """A video the subscription has seen, and what happened to it."""

    __tablename__ = "subscription_items"
    __table_args__ = (UniqueConstraint("subscription_id", "youtube_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    youtube_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    upload_date: Mapped[date | None]
    duration_s: Mapped[int | None]
    state: Mapped[ItemState] = mapped_column(str_enum(ItemState), index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("download_jobs.id", ondelete="SET NULL"))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    subscription: Mapped[Subscription] = relationship(back_populates="items")
    video: Mapped[Video | None] = relationship()
