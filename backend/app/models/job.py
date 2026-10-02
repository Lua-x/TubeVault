from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.video import str_enum

if TYPE_CHECKING:
    from app.models.video import Video


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(enum.StrEnum):
    METADATA = "metadata"
    DOWNLOADING = "downloading"
    POSTPROCESSING = "postprocessing"


class ErrorKind(enum.StrEnum):
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    LIVE = "live"
    UNKNOWN = "unknown"


ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSED)


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(1024))
    youtube_id: Mapped[str | None] = mapped_column(String(64), index=True)
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus), default=JobStatus.QUEUED, index=True
    )
    stage: Mapped[JobStage | None] = mapped_column(str_enum(JobStage))
    progress: Mapped[float] = mapped_column(default=0.0)
    downloaded_bytes: Mapped[int | None] = mapped_column(BigInteger)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    speed: Mapped[float | None]
    eta: Mapped[int | None]
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    next_attempt_at: Mapped[datetime | None]
    error_kind: Mapped[ErrorKind | None] = mapped_column(str_enum(ErrorKind))
    error_message: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(default=0)
    # Per-job overrides of the download settings (container, max height, …).
    options: Mapped[dict[str, Any]] = mapped_column(default=dict)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    video: Mapped[Video | None] = relationship()
