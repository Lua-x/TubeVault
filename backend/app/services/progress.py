"""Per-user watch progress."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Video, WatchProgress

# Counted as watched when this close to the end.
WATCHED_SHARE = 0.92
WATCHED_REMAINING_S = 30.0
# Below this position there is nothing worth resuming.
MIN_RESUME_S = 10.0


def progress_map(db: Session, user_id: int, video_ids: Iterable[int]) -> dict[int, WatchProgress]:
    ids = list(set(video_ids))
    if not ids:
        return {}
    rows = db.scalars(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id, WatchProgress.video_id.in_(ids)
        )
    )
    return {row.video_id: row for row in rows}


def _update(
    db: Session, user_id: int, video_id: int, change: Callable[[WatchProgress], None]
) -> WatchProgress:
    """Applies `change` to the user's progress row, creating it if needed.

    Two saves for a video watched for the first time can arrive together (a seek right
    after starting): the second insert then loses – so it retries as an update.
    """
    for attempt in range(2):
        row = db.get(WatchProgress, (user_id, video_id))
        if row is None:
            row = WatchProgress(user_id=user_id, video_id=video_id, position_s=0.0, watched=False)
            db.add(row)
        change(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
            continue
        return row
    raise AssertionError("unreachable")


def is_finished(position_s: float, duration_s: float | None) -> bool:
    if not duration_s or duration_s <= 0:
        return False
    return (
        position_s >= duration_s * WATCHED_SHARE or duration_s - position_s <= WATCHED_REMAINING_S
    )


def save_progress(
    db: Session, user_id: int, video: Video, position_s: float, duration_s: float | None = None
) -> WatchProgress:
    duration = duration_s or (float(video.duration_s) if video.duration_s else None)
    position = max(0.0, min(position_s, duration or position_s))

    def change(row: WatchProgress) -> None:
        row.position_s = position
        row.updated_at = datetime.now(UTC)
        # Re-watching parts of a finished video keeps it watched (like Jellyfin); only the
        # explicit "mark as unwatched" resets it.
        if is_finished(position, duration) and not row.watched:
            row.watched = True
            row.watched_at = datetime.now(UTC)

    return _update(db, user_id, video.id, change)


def set_watched(db: Session, user_id: int, video_id: int, watched: bool) -> WatchProgress:
    def change(row: WatchProgress) -> None:
        row.watched = watched
        row.watched_at = datetime.now(UTC) if watched else None
        row.position_s = 0.0
        row.updated_at = datetime.now(UTC)

    return _update(db, user_id, video_id, change)
