"""What the signed-in user watched, newest first."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.models import Video, VideoStatus, WatchProgress
from app.schemas.common import Page
from app.schemas.videos import VideoSummary
from app.services.access import visible_videos
from app.services.presenters import video_summaries

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
def history(
    user: CurrentUser,
    db: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[VideoSummary]:
    query = visible_videos(
        select(Video)
        .join(WatchProgress, WatchProgress.video_id == Video.id)
        .where(
            WatchProgress.user_id == user.id,
            Video.status == VideoStatus.READY,
            or_(WatchProgress.position_s > 0, WatchProgress.watched.is_(True)),
        ),
        user,
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    videos = db.scalars(
        query.options(selectinload(Video.channel))
        .order_by(WatchProgress.updated_at.desc(), Video.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return Page(items=video_summaries(db, user.id, list(videos)), total=total)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget(video_id: int, user: CurrentUser, db: DbSession) -> None:
    """Removes a video from the history – this also forgets where it stopped."""
    db.execute(
        delete(WatchProgress).where(
            WatchProgress.user_id == user.id, WatchProgress.video_id == video_id
        )
    )
    db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear(user: CurrentUser, db: DbSession) -> None:
    db.execute(delete(WatchProgress).where(WatchProgress.user_id == user.id))
    db.commit()
