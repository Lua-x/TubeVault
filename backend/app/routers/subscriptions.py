"""Subscriptions to channels and playlists."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import Context, CurrentUser, DbSession, require_can_add
from app.core.errors import clean_message
from app.models import (
    ACTIVE_JOB_STATUSES,
    DownloadJob,
    ItemState,
    JobStatus,
    Subscription,
    SubscriptionItem,
    User,
)
from app.schemas.subscriptions import (
    SubscriptionCreate,
    SubscriptionDetail,
    SubscriptionItemOut,
    SubscriptionOut,
    SubscriptionSettings,
    SubscriptionStats,
    SubscriptionUpdate,
)
from app.services.downloader import cleanup_temp
from app.services.schedule import as_utc, next_check
from app.services.subscriptions import delete_subscription, subscription_stats
from app.services.youtube_urls import InvalidVideoUrlError, parse_source_url
from app.workers.download_manager import job_payload, load_job

# View-only accounts and kids profiles don't manage downloads or subscriptions.
router = APIRouter(
    prefix="/subscriptions", tags=["subscriptions"], dependencies=[Depends(require_can_add)]
)


def _get(db: DbSession, subscription_id: int) -> Subscription:
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.id == subscription_id)
        .options(selectinload(Subscription.channel))
    )
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Abo nicht gefunden")
    return sub


def _out(sub: Subscription, stats: dict[str, int], ctx: Context) -> SubscriptionOut:
    out = SubscriptionOut.model_validate(sub)
    out.stats = SubscriptionStats.model_validate(stats)
    out.checking = ctx.checker.is_checking(sub.id)
    return out


CLEANUP_ADMIN_ONLY = "Aufräumregeln löschen Videos und können nur Administratoren ändern."


def _check_cleanup_rights(
    user: User, body: SubscriptionSettings, sub: Subscription | None = None
) -> None:
    """Cleanup rules delete files – like deleting videos, that is for admins only."""
    if user.is_admin:
        return
    current = (sub.keep_days, sub.keep_last) if sub else (None, None)
    if (body.keep_days, body.keep_last) != current:
        raise HTTPException(status.HTTP_403_FORBIDDEN, CLEANUP_ADMIN_ONLY)


def _apply_settings(sub: Subscription, body: SubscriptionSettings) -> None:
    sub.enabled = body.enabled
    sub.check_interval_minutes = body.check_interval_minutes
    sub.check_days = body.check_days
    sub.check_time = body.check_time
    sub.include_shorts = body.include_shorts
    sub.include_live = body.include_live
    sub.min_duration_s = body.min_duration_s or None
    sub.max_duration_s = body.max_duration_s or None
    sub.date_after = body.date_after
    sub.keep_days = body.keep_days
    sub.keep_last = body.keep_last
    sub.download_options = body.download_options.model_dump(exclude_none=True)


@router.get("")
def list_subscriptions(_: CurrentUser, db: DbSession, ctx: Context) -> list[SubscriptionOut]:
    subs = list(
        db.scalars(
            select(Subscription)
            .options(selectinload(Subscription.channel))
            .order_by(Subscription.title)
        )
    )
    stats = subscription_stats(db, [s.id for s in subs])
    return [_out(sub, stats[sub.id], ctx) for sub in subs]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_subscription(
    body: SubscriptionCreate, user: CurrentUser, db: DbSession, ctx: Context
) -> SubscriptionOut:
    _check_cleanup_rights(user, body)
    try:
        kind, url = parse_source_url(body.url)
    except InvalidVideoUrlError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    try:
        source = ctx.catalog.resolve(kind, url)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"YouTube konnte nicht gelesen werden: {clean_message(exc)}",
        ) from exc

    existing = db.scalar(
        select(Subscription).where(
            Subscription.kind == source.kind, Subscription.youtube_id == source.youtube_id
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"„{existing.title}“ ist bereits abonniert.")

    sub = Subscription(
        kind=source.kind,
        youtube_id=source.youtube_id,
        url=source.url,
        title=source.title,
        backfill=body.backfill,
        created_by_id=user.id,
        next_check_at=datetime.now(UTC),
    )
    _apply_settings(sub, body)
    db.add(sub)
    db.commit()
    ctx.scheduler.wake()
    ctx.events.publish("subscription.updated", subscription_id=sub.id)
    sub = _get(db, sub.id)
    return _out(sub, subscription_stats(db, [sub.id])[sub.id], ctx)


@router.get("/{subscription_id}")
def get_subscription(
    subscription_id: int,
    _: CurrentUser,
    db: DbSession,
    ctx: Context,
    limit: int = Query(default=200, ge=1, le=2000),
) -> SubscriptionDetail:
    sub = _get(db, subscription_id)
    items = db.scalars(
        select(SubscriptionItem)
        .where(SubscriptionItem.subscription_id == sub.id)
        .order_by(SubscriptionItem.first_seen_at.desc(), SubscriptionItem.id.desc())
        .limit(limit)
    )
    summary = _out(sub, subscription_stats(db, [sub.id])[sub.id], ctx)
    detail = SubscriptionDetail.model_validate(summary.model_dump())
    detail.items = [SubscriptionItemOut.model_validate(item) for item in items]
    return detail


@router.put("/{subscription_id}")
def update_subscription(
    subscription_id: int, body: SubscriptionUpdate, user: CurrentUser, db: DbSession, ctx: Context
) -> SubscriptionOut:
    sub = _get(db, subscription_id)
    _check_cleanup_rights(user, body, sub)
    was_enabled = sub.enabled
    timing = (sub.check_interval_minutes, sub.check_days, sub.check_time)
    _apply_settings(sub, body)
    retimed = timing != (sub.check_interval_minutes, sub.check_days, sub.check_time)
    if sub.enabled and not was_enabled:
        sub.next_check_at = datetime.now(UTC)
    elif sub.last_checked_at and retimed:
        # A new interval counts from the last check, a new schedule from now on.
        sub.next_check_at = next_check(
            interval_minutes=sub.check_interval_minutes,
            days=sub.check_days,
            at=sub.check_time,
            after=datetime.now(UTC) if sub.check_days else as_utc(sub.last_checked_at),
        )
    db.commit()
    ctx.scheduler.wake()
    if sub.has_cleanup:
        ctx.scheduler.request_cleanup()
    ctx.events.publish("subscription.updated", subscription_id=sub.id)
    return _out(_get(db, sub.id), subscription_stats(db, [sub.id])[sub.id], ctx)


@router.post("/{subscription_id}/check", status_code=status.HTTP_202_ACCEPTED)
def check_now(subscription_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> SubscriptionOut:
    sub = _get(db, subscription_id)
    ctx.scheduler.check_soon(sub.id)  # works for paused subscriptions too
    return _out(sub, subscription_stats(db, [sub.id])[sub.id], ctx)


@router.post("/{subscription_id}/reevaluate", status_code=status.HTTP_202_ACCEPTED)
def reevaluate(
    subscription_id: int, _: CurrentUser, db: DbSession, ctx: Context
) -> SubscriptionOut:
    """Forget filtered videos, so the next check judges them by the current filters."""
    sub = _get(db, subscription_id)
    for item in db.scalars(
        select(SubscriptionItem).where(
            SubscriptionItem.subscription_id == sub.id,
            SubscriptionItem.state == ItemState.FILTERED,
        )
    ):
        db.delete(item)
    db.commit()
    ctx.scheduler.check_soon(sub.id)
    return _out(sub, subscription_stats(db, [sub.id])[sub.id], ctx)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscription(
    subscription_id: int,
    user: CurrentUser,
    db: DbSession,
    ctx: Context,
    delete_videos: bool = False,
) -> None:
    if delete_videos and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Videos löschen dürfen nur Administratoren.")
    sub = _get(db, subscription_id)
    # Pending downloads of this subscription are dropped.
    jobs = db.scalars(
        select(DownloadJob).where(
            DownloadJob.subscription_id == sub.id, DownloadJob.status.in_(ACTIVE_JOB_STATUSES)
        )
    ).all()
    for job in jobs:
        if not ctx.downloads.cancel(job.id):
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            cleanup_temp(ctx.settings.temp_dir / f"job-{job.id}")
    db.commit()
    for job in jobs:
        fresh = load_job(db, job.id)
        if fresh is not None:
            ctx.events.publish("job.updated", job=job_payload(fresh))
    deleted = delete_subscription(db, ctx.settings.media_dir, sub, delete_videos=delete_videos)
    for video_id in deleted:
        ctx.events.publish("video.deleted", video_id=video_id)
    ctx.events.publish("subscription.deleted", subscription_id=subscription_id)
