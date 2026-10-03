"""Library: list, inspect, add and delete videos."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import CTE, ColumnElement, Select, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.core.deps import AdminUser, Context, CurrentUser, DbSession
from app.models import (
    ACTIVE_JOB_STATUSES,
    Channel,
    DownloadJob,
    User,
    Video,
    VideoStatus,
    WatchProgress,
)
from app.schemas.common import Page
from app.schemas.jobs import JobOut
from app.schemas.videos import (
    AddVideoRequest,
    ProgressUpdate,
    SegmentsOut,
    SponsorSegmentOut,
    VideoDetail,
    VideoSummary,
    WatchedUpdate,
    WatchState,
)
from app.services import sponsorblock
from app.services.access import ensure_visible, require_can_add, visible_videos
from app.services.app_settings import load_app_settings
from app.services.presenters import video_detail, video_summaries
from app.services.progress import MIN_RESUME_S, save_progress, set_watched
from app.services.search import search_ranking
from app.services.subscriptions import mark_video_removed
from app.services.upgrades import has_active_job, queue_upgrade
from app.services.videos import delete_video_files, video_file_exists
from app.services.youtube_urls import InvalidVideoUrlError, parse_video_url
from app.workers.download_manager import load_job

router = APIRouter(prefix="/videos", tags=["videos"])

SortOrder = Literal["relevance", "added", "newest", "oldest", "title"]
WatchedFilter = Literal["all", "unwatched", "watched", "in_progress"]


def _get_video(db: DbSession, video_id: int, user: User) -> Video:
    video = db.scalar(
        select(Video)
        .where(Video.id == video_id)
        .options(
            selectinload(Video.channel),
            selectinload(Video.subtitles),
            selectinload(Video.sponsor_segments),
        )
    )
    return ensure_visible(user, video)


def _watch_filter(query: Select[Any], user_id: int, watched: WatchedFilter) -> Any:
    if watched == "all":
        return query
    progress = aliased(WatchProgress)
    query = query.outerjoin(
        progress, (progress.video_id == Video.id) & (progress.user_id == user_id)
    )
    if watched == "watched":
        return query.where(progress.watched.is_(True))
    if watched == "in_progress":
        return query.where(progress.watched.is_(False), progress.position_s >= MIN_RESUME_S)
    return query.where(or_(progress.watched.is_(None), progress.watched.is_(False)))


@router.get("")
def list_videos(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    channel_id: int | None = None,
    watched: WatchedFilter = "all",
    sort: SortOrder | None = None,
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[VideoSummary]:
    query = visible_videos(select(Video), user).where(Video.status == VideoStatus.READY)
    if channel_id is not None:
        query = query.where(Video.channel_id == channel_id)
    query = _watch_filter(query, user.id, watched)

    search: CTE | None = None
    if q and q.strip():
        search = search_ranking(db.connection(), q)
        if search is None:  # no full-text index (not SQLite)
            pattern = f"%{q.strip().lower()}%"
            query = query.outerjoin(Channel).where(
                or_(
                    func.lower(Video.title).like(pattern),
                    func.lower(Video.description).like(pattern),
                    func.lower(Channel.name).like(pattern),
                )
            )
        else:
            query = query.join(search, search.c.id == Video.id)
    sort = sort or ("relevance" if search is not None else "added")

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    orders: dict[str, tuple[ColumnElement[Any], ...]] = {
        "added": (Video.added_at.desc(), Video.id.desc()),
        "newest": (Video.upload_date.desc(), Video.id.desc()),
        "oldest": (Video.upload_date.asc(), Video.id.asc()),
        "title": (func.lower(Video.title).asc(), Video.id.asc()),
    }
    if sort == "relevance" and search is not None:
        order: tuple[ColumnElement[Any], ...] = (search.c.rank.asc(), Video.id.desc())
    else:
        order = orders.get(sort, orders["added"])
    videos = db.scalars(
        query.options(selectinload(Video.channel)).order_by(*order).limit(limit).offset(offset)
    )
    return Page(items=video_summaries(db, user.id, videos), total=total)


@router.get("/{video_id}")
def get_video(video_id: int, user: CurrentUser, db: DbSession) -> VideoDetail:
    return video_detail(db, user.id, _get_video(db, video_id, user))


@router.get("/{video_id}/segments")
def sponsor_segments(video_id: int, user: CurrentUser, db: DbSession, ctx: Context) -> SegmentsOut:
    """SponsorBlock segments to skip; refreshed from SponsorBlock when they are stale.

    Offline (or after a failed fetch) the stored segments are used right away, so the
    video page never waits for the internet.
    """
    video = _get_video(db, video_id, user)
    options = load_app_settings(db).downloads
    if (
        options.sponsorblock_mode == "skip"
        and options.sponsorblock_categories
        and sponsorblock.is_stale(video)
        and not sponsorblock.recently_failed(video.youtube_id)
        and not ctx.connectivity.should_wait()
    ):
        sponsorblock.refresh(
            db,
            video,
            list(options.sponsorblock_categories),
            timeout=sponsorblock.INTERACTIVE_TIMEOUT,
        )
        db.refresh(video)
    wanted = set(options.sponsorblock_categories)
    return SegmentsOut(
        mode=options.sponsorblock_mode,
        cut=video.sponsorblock_cut,
        segments=[
            SponsorSegmentOut.model_validate(s)
            for s in video.sponsor_segments
            if s.category in wanted
        ],
    )


@router.put("/{video_id}/progress")
def update_progress(
    video_id: int, body: ProgressUpdate, user: CurrentUser, db: DbSession
) -> WatchState:
    video = ensure_visible(user, db.get(Video, video_id))
    return WatchState.model_validate(
        save_progress(db, user.id, video, body.position_s, body.duration_s)
    )


@router.put("/{video_id}/watched")
def update_watched(
    video_id: int, body: WatchedUpdate, user: CurrentUser, db: DbSession
) -> WatchState:
    ensure_visible(user, db.get(Video, video_id))
    return WatchState.model_validate(set_watched(db, user.id, video_id, body.watched))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def add_video(body: AddVideoRequest, user: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    require_can_add(user)
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

    options = body.model_dump(include={"container", "max_height", "comments"}, exclude_none=True)
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


@router.post("/{video_id}/redownload", status_code=status.HTTP_202_ACCEPTED)
def redownload(video_id: int, user: AdminUser, db: DbSession, ctx: Context) -> JobOut:
    """Download again with the current settings and replace the file, e.g. in better quality."""
    video = _get_video(db, video_id, user)
    if video.status is not VideoStatus.READY or not video_file_exists(
        ctx.settings.media_dir, video
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Videodatei fehlt.")
    if has_active_job(db, video):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieses Video wird bereits heruntergeladen.")
    job = queue_upgrade(db, video, requested_by=user.id)
    job.priority = 0
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
    user: AdminUser,
    db: DbSession,
    ctx: Context,
    delete_files: bool = True,
) -> None:
    video = _get_video(db, video_id, user)
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
    ctx.transcoder.purge(video.id)
    # Subscriptions must not download it again.
    mark_video_removed(db, video.id, "Gelöscht")
    db.delete(video)
    db.commit()
    ctx.events.publish("video.deleted", video_id=video_id)
