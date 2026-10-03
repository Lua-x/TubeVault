from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, computed_field

from app.models import ErrorKind, JobStage, JobStatus
from app.schemas.common import ApiModel
from app.schemas.videos import VideoSummary


class JobSubscription(ApiModel):
    id: int
    title: str


class JobOut(ApiModel):
    id: int
    url: str
    youtube_id: str | None
    status: JobStatus
    stage: JobStage | None
    progress: float
    downloaded_bytes: int | None
    total_bytes: int | None
    speed: float | None
    eta: int | None
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    error_kind: ErrorKind | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    video: VideoSummary | None
    subscription: JobSubscription | None
    options: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def upgrade(self) -> bool:
        """Replaces an existing file with a better version (the video stays playable)."""
        return bool(self.options.get("upgrade"))
