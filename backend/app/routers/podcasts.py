"""Podcast feeds for channels and playlists – addressed by a per-user token."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import AppConfig, Context, CurrentUser, DbSession
from app.core.urls import public_base
from app.models import Channel, Playlist, PlaylistItem, User, Video, VideoStatus
from app.routers.media import _media_file
from app.routers.playback import _source, audio_response
from app.services.access import can_see_channel, visible_videos
from app.services.podcasts import FEED_ITEMS, Feed, FeedItem, new_feed_token, render_feed
from app.services.subscriptions import channel_media_path
from app.services.transcode import audio_size_estimate

router = APIRouter(tags=["podcasts"])

RSS_TYPE = "application/rss+xml; charset=utf-8"
IMAGE_CACHE = "public, max-age=86400"


class PodcastAccess(BaseModel):
    enabled: bool
    # Feeds live below this address: …/channels/{id}.xml, …/playlists/{id}.xml
    base_url: str | None


def _access(request: Request, settings: AppConfig, user: User) -> PodcastAccess:
    if not user.feed_token:
        return PodcastAccess(enabled=False, base_url=None)
    return PodcastAccess(
        enabled=True,
        base_url=f"{public_base(request, settings)}/api/podcast/{user.feed_token}",
    )


@router.get("/podcasts")
def podcast_access(request: Request, user: CurrentUser, settings: AppConfig) -> PodcastAccess:
    return _access(request, settings, user)


@router.post("/podcasts/token")
def renew_token(
    request: Request, user: CurrentUser, db: DbSession, settings: AppConfig
) -> PodcastAccess:
    """Creates the podcast address – or a new one, which ends the old one."""
    user.feed_token = new_feed_token()
    db.commit()
    return _access(request, settings, user)


@router.delete("/podcasts/token", status_code=status.HTTP_204_NO_CONTENT)
def disable_token(user: CurrentUser, db: DbSession) -> None:
    user.feed_token = None
    db.commit()


# --- what podcast apps fetch (no session – the token decides) ---------------------------


def feed_user(token: str, db: DbSession) -> User:
    user = db.scalar(select(User).where(User.feed_token == token)) if len(token) >= 32 else None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unbekannter Feed")
    return user


FeedUser = Annotated[User, Depends(feed_user)]


def _feed(
    request: Request,
    settings: AppConfig,
    ctx: Context,
    user: User,
    *,
    title: str,
    description: str,
    link: str,
    image_url: str | None,
    videos: list[Video],
) -> Response:
    base = public_base(request, settings)
    feed_base = f"{base}/api/podcast/{user.feed_token}"
    items: list[FeedItem] = []
    ready: list[tuple[int, Path]] = []
    for video in videos:
        try:
            path = _media_file(settings.media_dir, video.file_path)
        except HTTPException:
            continue
        cached = ctx.transcoder.cached_audio(video.id, path)
        ready.append((video.id, path))
        items.append(
            FeedItem(
                guid=video.youtube_id,
                title=video.title,
                description=video.description or "",
                link=f"{base}/videos/{video.id}",
                published=video.upload_date or video.added_at,
                audio_url=f"{feed_base}/audio/{video.id}.m4a",
                audio_size=(
                    cached.stat().st_size if cached else audio_size_estimate(video.duration_s or 0)
                ),
                duration=video.duration_s,
                image_url=f"{feed_base}/images/videos/{video.id}.jpg"
                if video.thumbnail_path
                else None,
            )
        )
    ctx.podcasts.request(ready)
    body = render_feed(
        Feed(
            title=title,
            description=description,
            link=link,
            author=title,
            image_url=image_url,
            items=items,
        )
    )
    return Response(body, media_type=RSS_TYPE, headers={"Cache-Control": "private, max-age=300"})


@router.get("/podcast/{token}/channels/{channel_id}.xml")
def channel_feed(
    channel_id: int,
    request: Request,
    user: FeedUser,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> Response:
    channel = db.get(Channel, channel_id)
    if channel is None or not can_see_channel(user, channel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kanal nicht gefunden")
    videos = list(
        db.scalars(
            visible_videos(select(Video), user)
            .where(Video.channel_id == channel_id, Video.status == VideoStatus.READY)
            .order_by(Video.upload_date.desc(), Video.id.desc())
            .limit(FEED_ITEMS)
        )
    )
    base = public_base(request, settings)
    return _feed(
        request,
        settings,
        ctx,
        user,
        title=channel.name,
        description=channel.description or f"Videos von {channel.name} aus TubeVault",
        link=f"{base}/channels/{channel.id}",
        image_url=(
            f"{base}/api/podcast/{user.feed_token}/images/channels/{channel.id}.jpg"
            if channel.avatar_path
            else None
        ),
        videos=videos,
    )


@router.get("/podcast/{token}/playlists/{playlist_id}.xml")
def playlist_feed(
    playlist_id: int,
    request: Request,
    user: FeedUser,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> Response:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist nicht gefunden")
    videos = list(
        db.scalars(
            visible_videos(select(Video), user)
            .join(PlaylistItem, PlaylistItem.video_id == Video.id)
            .where(PlaylistItem.playlist_id == playlist.id, Video.status == VideoStatus.READY)
            .options(selectinload(Video.channel))
            .order_by(PlaylistItem.position, PlaylistItem.id)
            .limit(FEED_ITEMS)
        )
    )
    base = public_base(request, settings)
    first = next((v for v in videos if v.thumbnail_path), None)
    return _feed(
        request,
        settings,
        ctx,
        user,
        title=playlist.name,
        description=playlist.description or f"Playlist „{playlist.name}“ aus TubeVault",
        link=f"{base}/later" if playlist.is_watch_later else f"{base}/playlists/{playlist.id}",
        image_url=(
            f"{base}/api/podcast/{user.feed_token}/images/videos/{first.id}.jpg" if first else None
        ),
        videos=videos,
    )


@router.get("/podcast/{token}/audio/{video_id}.m4a")
def episode_audio(
    video_id: int, user: FeedUser, db: DbSession, settings: AppConfig, ctx: Context
) -> Response:
    return audio_response(ctx.transcoder, _source(db, settings, video_id, user)[1])


@router.get("/podcast/{token}/images/videos/{video_id}.jpg")
def episode_image(
    video_id: int, user: FeedUser, db: DbSession, settings: AppConfig
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None or not can_see_channel(user, video.channel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    path = _media_file(settings.media_dir, video.thumbnail_path)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": IMAGE_CACHE})


@router.get("/podcast/{token}/images/channels/{channel_id}.jpg")
def channel_image(
    channel_id: int, user: FeedUser, db: DbSession, settings: AppConfig
) -> FileResponse:
    if not can_see_channel(user, channel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    path = channel_media_path(settings.media_dir, db.get(Channel, channel_id), "avatar")
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": IMAGE_CACHE})
