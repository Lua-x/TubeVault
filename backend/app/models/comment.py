"""Comments saved with a video (optional), so they can be read without YouTube."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.video import Video


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    youtube_id: Mapped[str] = mapped_column(String(128))
    # YouTube ID of the comment this one answers; None for top-level comments.
    parent_id: Mapped[str | None] = mapped_column(String(128))
    # Order YouTube returned them in ("top comments"), replies oldest first.
    position: Mapped[int] = mapped_column(default=0)
    author: Mapped[str] = mapped_column(String(255))
    author_is_uploader: Mapped[bool] = mapped_column(default=False)
    author_is_verified: Mapped[bool] = mapped_column(default=False)
    text: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int | None]
    published_at: Mapped[datetime | None]
    is_pinned: Mapped[bool] = mapped_column(default=False)
    # Hearted by the creator.
    is_favorited: Mapped[bool] = mapped_column(default=False)

    video: Mapped[Video] = relationship(back_populates="comments")
