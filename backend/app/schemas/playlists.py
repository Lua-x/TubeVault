from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ApiModel
from app.schemas.videos import VideoSummary


class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bitte einen Namen angeben.")
        return value


class PlaylistOut(ApiModel):
    id: int
    name: str
    description: str | None
    is_watch_later: bool = False
    created_at: datetime
    updated_at: datetime
    video_count: int = 0
    duration_s: int = 0
    # Up to four videos for the cover mosaic.
    cover: list[VideoSummary] = Field(default_factory=list)
    contains: bool | None = None


class PlaylistDetail(PlaylistOut):
    videos: list[VideoSummary] = Field(default_factory=list)


class PlaylistItemIn(BaseModel):
    video_id: int


class PlaylistOrder(BaseModel):
    video_ids: list[int] = Field(max_length=10000)
