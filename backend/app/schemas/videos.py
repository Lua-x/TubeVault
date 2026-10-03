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


class WatchState(ApiModel):
    position_s: float
    watched: bool
    updated_at: datetime


class SponsorSegmentOut(ApiModel):
    category: str
    action: str
    start_s: float
    end_s: float


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
    # Filled per user by the routers.
    progress: WatchState | None = None


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
    sponsorblock_cut: bool
    sponsor_segments: list[SponsorSegmentOut]
    comments_fetched_at: datetime | None
    comment_count: int | None


class SegmentsOut(BaseModel):
    mode: str
    cut: bool
    segments: list[SponsorSegmentOut]


class ProgressUpdate(BaseModel):
    position_s: float = Field(ge=0, le=7 * 86400)
    duration_s: float | None = Field(default=None, ge=0, le=7 * 86400)


class WatchedUpdate(BaseModel):
    watched: bool


class ChannelCard(ChannelOut):
    video_count: int = 0
    unwatched_count: int = 0
    subscription_id: int | None = None
    latest_at: datetime | None = None


class ChannelDetail(ChannelCard):
    description: str | None


class HomeFeed(BaseModel):
    hero: VideoSummary | None
    continue_watching: list[VideoSummary]
    from_subscriptions: list[VideoSummary]
    recently_added: list[VideoSummary]
    channels: list[ChannelCard]


class AddVideoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    container: Container | None = None
    max_height: MaxHeight | None = None
    comments: bool | None = None
