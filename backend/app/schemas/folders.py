from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ApiModel
from app.schemas.videos import VideoSummary


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Bitte einen Namen angeben.")
    return value


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # None: directly in "Ordner".
    parent_id: int | None = None

    _strip = field_validator("name")(_clean_name)


class FolderUpdate(BaseModel):
    """Rename and/or move; only the fields that are sent change (parent_id null = to the top)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class FolderOut(ApiModel):
    id: int
    name: str
    parent_id: int | None
    created_at: datetime
    updated_at: datetime
    video_count: int = 0
    folder_count: int = 0
    # Up to four videos for the cover mosaic.
    cover: list[VideoSummary] = Field(default_factory=list)
    contains: bool | None = None


class FolderCrumb(BaseModel):
    id: int
    name: str


class FolderDetail(FolderOut):
    # The folders above, from the top down.
    path: list[FolderCrumb] = Field(default_factory=list)
    folders: list[FolderOut] = Field(default_factory=list)
    videos: list[VideoSummary] = Field(default_factory=list)
