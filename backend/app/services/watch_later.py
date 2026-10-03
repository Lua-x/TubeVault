""" "Später ansehen": a built-in playlist per user."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Playlist, PlaylistItem, User

NAME = "Später ansehen"


def watch_later(db: Session, user_id: int) -> Playlist:
    """The user's list, created on first use."""
    query = select(Playlist).where(Playlist.user_id == user_id, Playlist.is_watch_later.is_(True))
    playlist = db.scalar(query)
    if playlist is not None:
        return playlist
    db.add(Playlist(user_id=user_id, name=NAME, is_watch_later=True))
    try:
        db.commit()
    except IntegrityError:  # created by a parallel request just now
        db.rollback()
    playlist = db.scalar(query)
    assert playlist is not None
    return playlist


def remove_when_watched(db: Session, user: User, video_id: int) -> None:
    """A watched video leaves the list – unless the user wants to keep it there."""
    if user.preferences.get("watch_later_keep_watched"):
        return
    playlist_ids = select(Playlist.id).where(
        Playlist.user_id == user.id, Playlist.is_watch_later.is_(True)
    )
    db.execute(
        delete(PlaylistItem).where(
            PlaylistItem.video_id == video_id, PlaylistItem.playlist_id.in_(playlist_ids)
        )
    )
    db.commit()
