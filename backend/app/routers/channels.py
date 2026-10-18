"""Channels: list, details and artwork (avatar, banner)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.core.deps import Context, CurrentUser, DbSession
from app.models import Channel, User, Video, VideoStatus
from app.routers.media import IMAGE_CACHE
from app.schemas.videos import ChannelCard, ChannelDetail
from app.services.access import can_see_channel, visible_videos
from app.services.image_cache import channel_image
from app.services.presenters import channel_cards

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
    db: DbSession, ctx: Context, channel_id: int, kind: Literal["avatar", "banner"], user: User
) -> FileResponse:
    if not can_see_channel(user, channel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    image = channel_image(db.get(Channel, channel_id), kind)
    try:
        if image is None:
            raise FileNotFoundError(kind)
        path, _ = ctx.images.get(image, kind)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden") from exc
    # Asked for with a version in the address, like thumbnails (see routers/media.py).
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": IMAGE_CACHE})


@router.get("/{channel_id}/avatar")
def avatar(channel_id: int, user: CurrentUser, db: DbSession, ctx: Context) -> FileResponse:
    return _image(db, ctx, channel_id, "avatar", user)


@router.get("/{channel_id}/banner")
def banner(channel_id: int, user: CurrentUser, db: DbSession, ctx: Context) -> FileResponse:
    return _image(db, ctx, channel_id, "banner", user)
