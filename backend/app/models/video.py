from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.library import SponsorSegment
    from app.models.user import User


class VideoStatus(enum.StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"
    MISSING = "missing"


def str_enum(enum_cls: type[enum.StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_id: Mapped[str] = mapped_column(String(64), unique=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    upload_date: Mapped[date | None] = mapped_column(index=True)
    duration_s: Mapped[int | None]
    is_short: Mapped[bool] = mapped_column(default=False)
    was_live: Mapped[bool] = mapped_column(default=False)
    # Added by hand (not only through a subscription): never removed by cleanup.
    manual: Mapped[bool] = mapped_column(default=False)
    view_count: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[VideoStatus] = mapped_column(
        str_enum(VideoStatus), default=VideoStatus.PENDING, index=True
    )

    # Paths are relative to the media directory.
    file_path: Mapped[str | None] = mapped_column(String(1024))
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    filesize: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None]
    height: Mapped[int | None]
    vcodec: Mapped[str | None] = mapped_column(String(64))
    acodec: Mapped[str | None] = mapped_column(String(64))
    chapters: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    source_url: Mapped[str | None] = mapped_column(String(1024))

    added_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    downloaded_at: Mapped[datetime | None]
    # SponsorBlock: when segments were last fetched, and whether they were cut from the file.
    sponsorblock_fetched_at: Mapped[datetime | None]
    sponsorblock_cut: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    channel: Mapped[Channel | None] = relationship(back_populates="videos")
    added_by: Mapped[User | None] = relationship(back_populates="added_videos")
    subtitles: Mapped[list[Subtitle]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Subtitle.lang",
    )
    sponsor_segments: Mapped[list[SponsorSegment]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="SponsorSegment.start_s"
    )

    @property
    def has_thumbnail(self) -> bool:
        return bool(self.thumbnail_path)

    @property
    def container(self) -> str | None:
        if not self.file_path:
            return None
        suffix = self.file_path.rsplit(".", 1)[-1].lower()
        return suffix or None


class Subtitle(Base):
    __tablename__ = "subtitles"
    __table_args__ = (UniqueConstraint("video_id", "lang", "is_auto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    lang: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(128))
    is_auto: Mapped[bool] = mapped_column(default=False)
    file_path: Mapped[str] = mapped_column(String(1024))

    video: Mapped[Video] = relationship(back_populates="subtitles")
