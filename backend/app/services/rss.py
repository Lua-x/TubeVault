"""Find new uploads quickly through YouTube's RSS feeds.

A full subscription check lists a channel through yt-dlp – thorough, but heavy, so it
runs every few hours. Every channel and playlist also has a small Atom feed with its
latest 15 uploads. Looking at it every 15 minutes is cheap; only when it shows a video
TubeVault does not know yet, the full check is moved forward. The feed is only a hint:
the full check keeps running on its own schedule, since the feed shows few videos and
mixes in Shorts and streams.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import classify_error
from app.models import ErrorKind, Subscription, SubscriptionItem, SubscriptionKind
from app.services.app_settings import load_app_settings
from app.services.connectivity import Connectivity

log = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
FEED_TIMEOUT = 10
MAX_FEED_BYTES = 2 * 1024 * 1024
INTERVAL = timedelta(minutes=15)
PER_ROUND = 10
_VIDEO_ID = re.compile(r"<yt:videoId>([\w-]{11})</yt:videoId>")

FeedFetcher = Callable[[str], list[str]]


def feed_url(kind: SubscriptionKind, youtube_id: str) -> str:
    key = "playlist_id" if kind is SubscriptionKind.PLAYLIST else "channel_id"
    return f"{FEED_URL}?{urllib.parse.urlencode({key: youtube_id})}"


def video_ids(feed: str) -> list[str]:
    """The video IDs in a feed. A pattern instead of an XML parser: nothing to exploit."""
    return list(dict.fromkeys(_VIDEO_ID.findall(feed)))


def fetch_feed_ids(url: str) -> list[str]:
    request = urllib.request.Request(url, headers={"User-Agent": "TubeVault"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=FEED_TIMEOUT) as response:  # noqa: S310 – fixed https URL
        data: bytes = response.read(MAX_FEED_BYTES)
    return video_ids(data.decode("utf-8", errors="replace"))


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class RssWatcher:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        connectivity: Connectivity | None = None,
        fetch: FeedFetcher = fetch_feed_ids,
        interval: timedelta = INTERVAL,
    ) -> None:
        self._sessions = sessions
        self._connectivity = connectivity
        self._fetch = fetch
        self._interval = interval
        self._checked: dict[int, datetime] = {}
        # Feed entries that already moved a check forward. Whatever the full check did not
        # pick up (e.g. Shorts when they are excluded) must not trigger it again and again.
        self._seen: dict[int, set[str]] = {}

    def run_round(self) -> list[int]:
        """Look at the feeds that are due. Returns the subscriptions whose check moved up."""
        if self._connectivity and self._connectivity.should_wait():
            return []
        now = utcnow()
        with self._sessions() as db:
            if not load_app_settings(db).subscriptions.rss:
                return []
            subs = [
                sub
                for sub in db.scalars(select(Subscription).where(Subscription.enabled.is_(True)))
                # Only after the first full check, and not when a full check is due anyway.
                if sub.last_checked_at is not None
                and (sub.next_check_at is None or _aware(sub.next_check_at) > now)  # type: ignore[operator]
                and now - self._checked.get(sub.id, datetime.min.replace(tzinfo=UTC))
                >= self._interval
            ]
            subs.sort(key=lambda sub: self._checked.get(sub.id, datetime.min.replace(tzinfo=UTC)))
            moved: list[int] = []
            for sub in subs[:PER_ROUND]:
                try:
                    ids = self._fetch(feed_url(sub.kind, sub.youtube_id))
                except Exception as exc:
                    offline = (
                        classify_error(exc) is ErrorKind.NETWORK
                        and self._connectivity is not None
                        and self._connectivity.confirm_offline()
                    )
                    if offline:
                        break
                    log.debug("RSS-Feed von „%s“ nicht lesbar: %s", sub.title, exc)
                    self._checked[sub.id] = now
                    continue
                self._checked[sub.id] = now
                if not ids:
                    continue
                known = set(
                    db.scalars(
                        select(SubscriptionItem.youtube_id).where(
                            SubscriptionItem.subscription_id == sub.id,
                            SubscriptionItem.youtube_id.in_(ids),
                        )
                    )
                )
                new = set(ids) - known - self._seen.get(sub.id, set())
                if new:
                    self._seen.setdefault(sub.id, set()).update(new)
                    sub.next_check_at = now
                    moved.append(sub.id)
                    log.info("Abo „%s“: neues Video im RSS-Feed – Prüfung vorgezogen", sub.title)
            db.commit()
        if self._connectivity and moved:
            self._connectivity.report_success()
        return moved

    def forget(self, subscription_id: int) -> None:
        self._checked.pop(subscription_id, None)
        self._seen.pop(subscription_id, None)
