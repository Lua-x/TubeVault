"""The start page: hero, continue watching, new from subscriptions, channels."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.models import (
    Channel,
    ItemState,
    SubscriptionItem,
    Video,
    VideoStatus,
    WatchProgress,
)
from app.schemas.videos import HomeFeed
from app.services.access import video_filter
from app.services.presenters import channel_cards, video_summaries
from app.services.progress import MIN_RESUME_S

router = APIRouter(tags=["home"])

ROW_SIZE = 24


@router.get("/home")
def home(user: CurrentUser, db: DbSession) -> HomeFeed:
    ready: ColumnElement[bool] = Video.status == VideoStatus.READY
    visible = video_filter(user)
    if visible is not None:
        ready = and_(ready, visible)
    with_channel = selectinload(Video.channel)

    continuing = list(
        db.scalars(
            select(Video)
            .join(WatchProgress, WatchProgress.video_id == Video.id)
            .where(
                ready,
                WatchProgress.user_id == user.id,
                WatchProgress.watched.is_(False),
                WatchProgress.position_s >= MIN_RESUME_S,
            )
            .options(with_channel)
            .order_by(WatchProgress.updated_at.desc())
            .limit(ROW_SIZE)
        )
    )

    from_subscriptions = list(
        db.scalars(
            select(Video)
            .where(
                ready,
                Video.id.in_(
                    select(SubscriptionItem.video_id).where(
                        SubscriptionItem.state == ItemState.DOWNLOADED
                    )
                ),
            )
            .options(with_channel)
            .order_by(Video.downloaded_at.desc(), Video.id.desc())
            .limit(ROW_SIZE)
        )
    )

    recent_query = select(Video).where(ready).options(with_channel)
    if from_subscriptions:
        recent_query = recent_query.where(Video.manual.is_(True))
    recently_added = list(
        db.scalars(recent_query.order_by(Video.added_at.desc(), Video.id.desc()).limit(ROW_SIZE))
    )

    latest = (
        select(Video.channel_id, func.max(Video.downloaded_at).label("latest"))
        .where(ready, Video.channel_id.is_not(None))
        .group_by(Video.channel_id)
        .subquery()
    )
    channels = list(
        db.scalars(
            select(Channel)
            .join(latest, latest.c.channel_id == Channel.id)
            .order_by(latest.c.latest.desc())
            .limit(ROW_SIZE)
        )
    )

    continuing_out = video_summaries(db, user.id, continuing)
    subs_out = video_summaries(db, user.id, from_subscriptions)
    recent_out = video_summaries(db, user.id, recently_added)

    hero = continuing_out[0] if continuing_out else None
    if hero is None:
        fresh = [v for v in subs_out + recent_out if not (v.progress and v.progress.watched)]
        everything = subs_out + recent_out
        hero = fresh[0] if fresh else (everything[0] if everything else None)

    return HomeFeed(
        hero=hero,
        continue_watching=continuing_out,
        from_subscriptions=subs_out,
        recently_added=recent_out,
        channels=channel_cards(db, user.id, channels),
    )
