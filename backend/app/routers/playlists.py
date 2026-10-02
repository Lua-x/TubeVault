"""Personal playlists of the signed-in user."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.models import Playlist, PlaylistItem, User, Video, VideoStatus
from app.schemas.playlists import (
    PlaylistDetail,
    PlaylistIn,
    PlaylistItemIn,
    PlaylistOrder,
    PlaylistOut,
)
from app.services.presenters import video_summaries

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _get(db: DbSession, user: User, playlist_id: int) -> Playlist:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist nicht gefunden")
    return playlist


def _ready_videos(db: DbSession, playlist: Playlist) -> list[Video]:
    return list(
        db.scalars(
            select(Video)
            .join(PlaylistItem, PlaylistItem.video_id == Video.id)
            .where(PlaylistItem.playlist_id == playlist.id, Video.status == VideoStatus.READY)
            .options(selectinload(Video.channel))
            .order_by(PlaylistItem.position, PlaylistItem.id)
        )
    )


def _out(db: DbSession, user: User, playlist: Playlist, video_id: int | None = None) -> PlaylistOut:
    videos = _ready_videos(db, playlist)
    out = PlaylistOut.model_validate(playlist)
    out.video_count = len(videos)
    out.duration_s = sum(v.duration_s or 0 for v in videos)
    out.cover = video_summaries(db, user.id, videos[:4])
    if video_id is not None:
        out.contains = any(v.id == video_id for v in videos)
    return out


def _touch(playlist: Playlist) -> None:
    playlist.updated_at = datetime.now(UTC)


@router.get("")
def list_playlists(
    user: CurrentUser, db: DbSession, video_id: int | None = None
) -> list[PlaylistOut]:
    playlists = db.scalars(
        select(Playlist)
        .where(Playlist.user_id == user.id)
        .order_by(Playlist.updated_at.desc(), Playlist.id.desc())
    )
    return [_out(db, user, p, video_id) for p in playlists]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_playlist(body: PlaylistIn, user: CurrentUser, db: DbSession) -> PlaylistOut:
    playlist = Playlist(user_id=user.id, name=body.name, description=body.description)
    db.add(playlist)
    db.commit()
    return _out(db, user, playlist)


@router.get("/{playlist_id}")
def get_playlist(playlist_id: int, user: CurrentUser, db: DbSession) -> PlaylistDetail:
    playlist = _get(db, user, playlist_id)
    detail = PlaylistDetail.model_validate(_out(db, user, playlist).model_dump())
    detail.videos = video_summaries(db, user.id, _ready_videos(db, playlist))
    return detail


@router.patch("/{playlist_id}")
def update_playlist(
    playlist_id: int, body: PlaylistIn, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    playlist = _get(db, user, playlist_id)
    playlist.name = body.name
    playlist.description = body.description
    db.commit()
    return _out(db, user, playlist)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(playlist_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(_get(db, user, playlist_id))
    db.commit()


@router.post("/{playlist_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    playlist_id: int, body: PlaylistItemIn, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    playlist = _get(db, user, playlist_id)
    if db.get(Video, body.video_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video nicht gefunden")
    exists = db.scalar(
        select(PlaylistItem.id).where(
            PlaylistItem.playlist_id == playlist.id, PlaylistItem.video_id == body.video_id
        )
    )
    if exists is None:
        last = db.scalar(
            select(func.max(PlaylistItem.position)).where(PlaylistItem.playlist_id == playlist.id)
        )
        db.add(
            PlaylistItem(playlist_id=playlist.id, video_id=body.video_id, position=(last or 0) + 1)
        )
        _touch(playlist)
        db.commit()
    return _out(db, user, playlist, body.video_id)


@router.delete("/{playlist_id}/items/{video_id}")
def remove_item(playlist_id: int, video_id: int, user: CurrentUser, db: DbSession) -> PlaylistOut:
    playlist = _get(db, user, playlist_id)
    item = db.scalar(
        select(PlaylistItem).where(
            PlaylistItem.playlist_id == playlist.id, PlaylistItem.video_id == video_id
        )
    )
    if item is not None:
        db.delete(item)
        _touch(playlist)
        db.commit()
    return _out(db, user, playlist, video_id)


@router.put("/{playlist_id}/order")
def reorder(playlist_id: int, body: PlaylistOrder, user: CurrentUser, db: DbSession) -> PlaylistOut:
    playlist = _get(db, user, playlist_id)
    items = {
        item.video_id: item
        for item in db.scalars(select(PlaylistItem).where(PlaylistItem.playlist_id == playlist.id))
    }
    position = 0
    for video_id in body.video_ids:
        item = items.pop(video_id, None)
        if item is not None:
            position += 1
            item.position = position
    for item in sorted(items.values(), key=lambda i: i.position):  # not in the list: keep at end
        position += 1
        item.position = position
    _touch(playlist)
    db.commit()
    return _out(db, user, playlist)
