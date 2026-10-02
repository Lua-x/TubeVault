"""Turning ORM objects into API models with the current user's state attached."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Channel, Subscription, SubscriptionKind, Video, VideoStatus, WatchProgress
from app.schemas.videos import ChannelCard, VideoDetail, VideoSummary, WatchState
from app.services.progress import progress_map


def video_summaries(db: Session, user_id: int, videos: Iterable[Video]) -> list[VideoSummary]:
    items = list(videos)
    progress = progress_map(db, user_id, (v.id for v in items))
    out: list[VideoSummary] = []
    for video in items:
        summary = VideoSummary.model_validate(video)
        state = progress.get(video.id)
        summary.progress = WatchState.model_validate(state) if state else None
        out.append(summary)
    return out


def video_detail(db: Session, user_id: int, video: Video) -> VideoDetail:
    detail = VideoDetail.model_validate(video)
    state = progress_map(db, user_id, [video.id]).get(video.id)
    detail.progress = WatchState.model_validate(state) if state else None
    return detail


def channel_cards(db: Session, user_id: int, channels: Sequence[Channel]) -> list[ChannelCard]:
    ids = [c.id for c in channels]
    if not ids:
        return []
    stats: dict[int, dict[str, Any]] = {
        row.channel_id: {"count": row.count, "unwatched": row.unwatched, "latest": row.latest}
        for row in db.execute(
            select(
                Video.channel_id,
                func.count(Video.id).label("count"),
                func.sum(case((WatchProgress.watched.is_(True), 0), else_=1)).label("unwatched"),
                func.max(Video.downloaded_at).label("latest"),
            )
            .outerjoin(
                WatchProgress,
                (WatchProgress.video_id == Video.id) & (WatchProgress.user_id == user_id),
            )
            .where(Video.channel_id.in_(ids), Video.status == VideoStatus.READY)
            .group_by(Video.channel_id)
        )
    }
    subs = {
        row.channel_id: row.id
        for row in db.execute(
            select(Subscription.channel_id, Subscription.id).where(
                Subscription.channel_id.in_(ids), Subscription.kind == SubscriptionKind.CHANNEL
            )
        )
    }
    cards: list[ChannelCard] = []
    for channel in channels:
        card = ChannelCard.model_validate(channel)
        stat = stats.get(channel.id, {})
        card.video_count = int(stat.get("count") or 0)
        card.unwatched_count = int(stat.get("unwatched") or 0)
        latest = stat.get("latest")
        card.latest_at = latest if isinstance(latest, datetime) else None
        card.subscription_id = subs.get(channel.id)
        cards.append(card)
    return cards
