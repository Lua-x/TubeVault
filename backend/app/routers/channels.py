"""Channels: list, details and artwork (avatar, banner)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.core.deps import AppConfig, CurrentUser, DbSession
from app.models import Channel, User, Video, VideoStatus
from app.schemas.videos import ChannelCard, ChannelDetail
from app.services.access import can_see_channel, visible_videos
from app.services.presenters import channel_cards
from app.services.subscriptions import channel_media_path

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("")
def list_channels(user: CurrentUser, db: DbSession) -> list[ChannelCard]:
    with_videos = (
        visible_videos(select(Video.channel_id), user)
        .where(Video.status == VideoStatus.READY)
        .distinct()
        .subquery()
    )
    channels = list(
        db.scalars(
            select(Channel)
            .where(Channel.id.in_(select(with_videos.c.channel_id)))
            .order_by(func.lower(Channel.name))
        )
    )
    return channel_cards(db, user.id, channels)


@router.get("/{channel_id}")
def get_channel(channel_id: int, user: CurrentUser, db: DbSession) -> ChannelDetail:
    channel = db.get(Channel, channel_id)
    if channel is None or not can_see_channel(user, channel.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kanal nicht gefunden")
    card = channel_cards(db, user.id, [channel])[0]
    return ChannelDetail(**card.model_dump(), description=channel.description)


def _image(
    db: DbSession, settings: AppConfig, channel_id: int, kind: str, user: User
) -> FileResponse:
    if not can_see_channel(user, channel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    path = channel_media_path(settings.media_dir, db.get(Channel, channel_id), kind)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/{channel_id}/avatar")
def avatar(channel_id: int, user: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    return _image(db, settings, channel_id, "avatar", user)


@router.get("/{channel_id}/banner")
def banner(channel_id: int, user: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    return _image(db, settings, channel_id, "banner", user)
