from __future__ import annotations

from datetime import datetime

from app.models import ErrorKind, JobStage, JobStatus
from app.schemas.common import ApiModel
from app.schemas.videos import VideoSummary


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
