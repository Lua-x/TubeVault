from __future__ import annotations

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models import ItemState, SubscriptionKind
from app.schemas.common import ApiModel
from app.schemas.videos import ChannelOut
from app.services.app_settings import Container, MaxHeight


class SubscriptionDownloadOptions(BaseModel):
    """Overrides for the global download settings. Unset fields use the global value."""

    container: Container | None = None
    max_height: MaxHeight | None = None
    prefer_h264: bool | None = None


class SubscriptionSettings(BaseModel):
    enabled: bool = True
    check_interval_minutes: int = Field(default=360, ge=15, le=10080)
    include_shorts: bool = False
    include_live: bool = False
    min_duration_s: int | None = Field(default=None, ge=0, le=86400)
    max_duration_s: int | None = Field(default=None, ge=0, le=86400)
    date_after: date | None = None
    keep_days: int | None = Field(default=None, ge=1, le=3650)
    keep_last: int | None = Field(default=None, ge=1, le=10000)
    download_options: SubscriptionDownloadOptions = Field(
        default_factory=SubscriptionDownloadOptions
    )

    @model_validator(mode="after")
    def _check_durations(self) -> Self:
        if (
            self.min_duration_s
            and self.max_duration_s
            and self.min_duration_s > self.max_duration_s
        ):
            raise ValueError("Die Mindestdauer ist größer als die Maximaldauer.")
        return self


class SubscriptionCreate(SubscriptionSettings):
    url: str = Field(min_length=1, max_length=1024)
    # Existing videos taken by the first check; None = all of them.
    backfill: int | None = Field(default=5, ge=0, le=10000)


class SubscriptionUpdate(SubscriptionSettings):
    """Full replacement of the editable settings (the form always sends everything)."""


class SubscriptionStats(BaseModel):
    queued: int = 0
    downloaded: int = 0
    filtered: int = 0
    skipped: int = 0
    failed: int = 0
    removed: int = 0


class SubscriptionOut(ApiModel):
    id: int
    kind: SubscriptionKind
    youtube_id: str
    url: str
    title: str
    enabled: bool
    check_interval_minutes: int
    last_checked_at: datetime | None
    next_check_at: datetime | None
    last_check_error: str | None
    backfill: int | None
    include_shorts: bool
    include_live: bool
    min_duration_s: int | None
    max_duration_s: int | None
    date_after: date | None
    keep_days: int | None
    keep_last: int | None
    download_options: SubscriptionDownloadOptions
    created_at: datetime
    channel: ChannelOut | None
    stats: SubscriptionStats = Field(default_factory=SubscriptionStats)
    checking: bool = False


class SubscriptionItemOut(ApiModel):
    id: int
    youtube_id: str
    title: str | None
    upload_date: date | None
    duration_s: int | None
    state: ItemState
    reason: str | None
    video_id: int | None
    job_id: int | None
    first_seen_at: datetime


class SubscriptionDetail(SubscriptionOut):
    items: list[SubscriptionItemOut] = Field(default_factory=list)
