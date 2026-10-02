"""Library: list, inspect, add and delete videos."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import AdminUser, Context, CurrentUser, DbSession
from app.models import ACTIVE_JOB_STATUSES, Channel, DownloadJob, Video, VideoStatus
from app.schemas.common import Page
from app.schemas.jobs import JobOut
from app.schemas.videos import AddVideoRequest, VideoDetail, VideoSummary
from app.services.subscriptions import mark_video_removed
from app.services.videos import delete_video_files, video_file_exists
from app.services.youtube_urls import InvalidVideoUrlError, parse_video_url
from app.workers.download_manager import load_job

router = APIRouter(prefix="/videos", tags=["videos"])

SortOrder = Literal["added", "newest", "oldest", "title"]


def _get_video(db: DbSession, video_id: int) -> Video:
    video = db.scalar(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.channel), selectinload(Video.subtitles))
    )
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video nicht gefunden")
    return video


@router.get("")
def list_videos(
    _: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    channel_id: int | None = None,
    sort: SortOrder = "added",
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[VideoSummary]:
    query = select(Video).where(Video.status == VideoStatus.READY)
    if channel_id is not None:
        query = query.where(Video.channel_id == channel_id)
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.outerjoin(Channel).where(
            or_(
                func.lower(Video.title).like(pattern),
                func.lower(Video.description).like(pattern),
                func.lower(Channel.name).like(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    orders: dict[str, tuple[ColumnElement[Any], ...]] = {
        "added": (Video.added_at.desc(), Video.id.desc()),
        "newest": (Video.upload_date.desc(), Video.id.desc()),
        "oldest": (Video.upload_date.asc(), Video.id.asc()),
        "title": (func.lower(Video.title).asc(), Video.id.asc()),
    }
    order = orders[sort]
    videos = db.scalars(
        query.options(selectinload(Video.channel)).order_by(*order).limit(limit).offset(offset)
    )
    return Page(items=[VideoSummary.model_validate(v) for v in videos], total=total)


@router.get("/{video_id}")
def get_video(video_id: int, _: CurrentUser, db: DbSession) -> VideoDetail:
    return VideoDetail.model_validate(_get_video(db, video_id))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def add_video(body: AddVideoRequest, user: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    try:
        url, youtube_id = parse_video_url(body.url)
    except InvalidVideoUrlError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    existing = db.scalar(select(Video).where(Video.youtube_id == youtube_id))
    if (
        existing is not None
        and existing.status is VideoStatus.READY
        and video_file_exists(ctx.settings.media_dir, existing)
    ):
        if not existing.manual:
            # Added by hand on purpose: keep it even when a subscription cleans up.
            existing.manual = True
            db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieses Video ist bereits in der Bibliothek.")
    active = db.scalar(
        select(DownloadJob).where(
            DownloadJob.youtube_id == youtube_id, DownloadJob.status.in_(ACTIVE_JOB_STATUSES)
        )
    )
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieses Video wird bereits heruntergeladen.")

    options = body.model_dump(include={"container", "max_height"}, exclude_none=True)
    job = DownloadJob(
        url=url,
        youtube_id=youtube_id,
        video_id=existing.id if existing else None,
        options=options,
        requested_by_id=user.id,
    )
    db.add(job)
    db.commit()
    fresh = load_job(db, job.id)
    assert fresh is not None
    payload = JobOut.model_validate(fresh)
    ctx.events.publish("job.updated", job=payload.model_dump(mode="json"))
    ctx.downloads.wake()
    return payload


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    _: AdminUser,
    db: DbSession,
    ctx: Context,
    delete_files: bool = True,
) -> None:
    video = _get_video(db, video_id)
    active = db.scalars(
        select(DownloadJob).where(
            DownloadJob.video_id == video.id, DownloadJob.status.in_(ACTIVE_JOB_STATUSES)
        )
    ).all()
    if any(ctx.downloads.is_running(job.id) for job in active):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Das Video wird gerade heruntergeladen. Bitte erst abbrechen."
        )
    for job in active:
        db.delete(job)
    if delete_files:
        delete_video_files(ctx.settings.media_dir, video)
    # Subscriptions must not download it again.
    mark_video_removed(db, video.id, "Gelöscht")
    db.delete(video)
    db.commit()
    ctx.events.publish("video.deleted", video_id=video_id)
