"""What a user may see: all channels, or only the ones chosen for them.

Every query that shows videos or channels to a user goes through here, so a kids
profile cannot reach other videos – not through lists, search, playlists, the video
page, nor by requesting a file or stream directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.orm import Session

from app.models import User, Video, user_channels
from app.services.app_settings import youtube_enabled

NOT_FOUND = "Video nicht gefunden"
YOUTUBE_OFF = "Der YouTube-Downloader ist ausgeschaltet – TubeVault läuft als reiner Media-Server."


def allowed_channels(user: User) -> Select[tuple[int]]:
    return select(user_channels.c.channel_id).where(user_channels.c.user_id == user.id)


def video_filter(user: User) -> ColumnElement[bool] | None:
    """A WHERE condition for videos, or None when the user sees everything."""
    if not user.restricted:
        return None
    return Video.channel_id.in_(allowed_channels(user))


def channel_filter(user: User, column: Any) -> ColumnElement[bool] | None:
    if not user.restricted:
        return None
    return column.in_(allowed_channels(user))  # type: ignore[no-any-return]


def visible_videos[S: Select[Any]](query: S, user: User) -> S:
    condition = video_filter(user)
    return query if condition is None else query.where(condition)


def can_see_channel(user: User, channel_id: int | None) -> bool:
    if not user.restricted:
        return True
    return channel_id is not None and channel_id in {channel.id for channel in user.channels}


def can_see_video(user: User, video: Video) -> bool:
    return can_see_channel(user, video.channel_id)


def ensure_visible(user: User, video: Video | None) -> Video:
    """404 for hidden videos – the same answer as for videos that don't exist."""
    if video is None or not can_see_video(user, video):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return video


def require_can_add(user: User) -> None:
    if not user.can_add:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Dein Konto darf keine Videos hinzufügen oder abonnieren."
        )


def require_youtube(db: Session) -> None:
    """Everything that would fetch from YouTube – refused in media-server mode."""
    if not youtube_enabled(db):
        raise HTTPException(status.HTTP_409_CONFLICT, YOUTUBE_OFF)
