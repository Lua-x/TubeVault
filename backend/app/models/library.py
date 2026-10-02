"""Per-user library state: watch progress and personal playlists. Plus SponsorBlock segments."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

if TYPE_CHECKING:
    from app.models.video import Video


class WatchProgress(Base):
    __tablename__ = "watch_progress"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position_s: Mapped[float] = mapped_column(default=0.0)
    watched: Mapped[bool] = mapped_column(default=False)
    watched_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, index=True)


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    items: Mapped[list[PlaylistItem]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PlaylistItem.position",
    )


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "video_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), index=True
    )
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    added_at: Mapped[datetime] = mapped_column(default=utcnow)

    playlist: Mapped[Playlist] = relationship(back_populates="items")
    video: Mapped[Video] = relationship()


class SponsorSegment(Base):
    __tablename__ = "sponsor_segments"
    __table_args__ = (UniqueConstraint("video_id", "uuid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    uuid: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16), default="skip")
    start_s: Mapped[float]
    end_s: Mapped[float]
