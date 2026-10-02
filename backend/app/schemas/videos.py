from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import VideoStatus
from app.schemas.common import ApiModel
from app.services.app_settings import Container, MaxHeight


class ChannelOut(ApiModel):
    id: int
    youtube_id: str
    name: str
    handle: str | None
    url: str | None
    has_avatar: bool
    has_banner: bool
    updated_at: datetime


class SubtitleOut(ApiModel):
    id: int
    lang: str
    label: str
    is_auto: bool


class Chapter(BaseModel):
    start: float
    end: float
    title: str


class VideoSummary(ApiModel):
    id: int
    youtube_id: str
    title: str
    channel: ChannelOut | None
    duration_s: int | None
    upload_date: date | None
    status: VideoStatus
    is_short: bool
    was_live: bool
    has_thumbnail: bool
    added_at: datetime
    updated_at: datetime


class VideoDetail(VideoSummary):
    description: str | None
    view_count: int | None
    width: int | None
    height: int | None
    vcodec: str | None
    acodec: str | None
    filesize: int | None
    container: str | None
    chapters: list[Chapter]
    subtitles: list[SubtitleOut]
    source_url: str | None
    downloaded_at: datetime | None


class AddVideoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    container: Container | None = None
    max_height: MaxHeight | None = None
