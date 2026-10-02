"""Checks subscriptions when they are due and runs the cleanup regularly."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.models import Subscription
from app.services.catalog import Catalog
from app.services.subscriptions import (
    SubscriptionChecker,
    refresh_channel_artwork,
    run_cleanup,
)

log = logging.getLogger(__name__)

CLEANUP_INTERVAL = timedelta(hours=1)
CHECKS_PER_ROUND = 3


def utcnow() -> datetime:
    return datetime.now(UTC)


class SubscriptionScheduler:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        events: EventBus,
        checker: SubscriptionChecker,
        catalog: Catalog,
        poll_interval: float = 30.0,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._events = events
        self._checker = checker
        self._catalog = catalog
        self._poll_interval = poll_interval
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cleanup: datetime | None = None
        self._forced: set[int] = set()
        self._forced_lock = threading.Lock()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="subscriptions", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def wake(self) -> None:
        self._wake.set()

    def check_soon(self, subscription_id: int) -> None:
        """Check this subscription in the next round, even if it is paused or not due."""
        with self._forced_lock:
            self._forced.add(subscription_id)
        self._wake.set()

    def request_cleanup(self) -> None:
        """Run the cleanup soon, e.g. after a subscription download finished."""
        self._last_cleanup = None
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_due()
                self._maybe_cleanup()
            except Exception:
                log.exception("Fehler im Abo-Scheduler")
            self._wake.wait(self._poll_interval)
            self._wake.clear()

    def _run_due(self) -> None:
        with self._forced_lock:
            forced, self._forced = self._forced, set()
        for subscription_id in sorted(forced):
            if self._stop.is_set():
                return
            self._checker.check(subscription_id)
        with self._sessions() as db:
            due = list(
                db.scalars(
                    select(Subscription.id)
                    .where(
                        Subscription.enabled.is_(True),
                        or_(
                            Subscription.next_check_at.is_(None),
                            Subscription.next_check_at <= utcnow(),
                        ),
                    )
                    .order_by(Subscription.next_check_at.is_not(None), Subscription.next_check_at)
                    .limit(CHECKS_PER_ROUND)
                )
            )
        for subscription_id in due:
            if self._stop.is_set():
                return
            self._checker.check(subscription_id)
        if due:
            self._wake.set()  # more might be due; go again right away

    def _maybe_cleanup(self) -> None:
        now = utcnow()
        if self._last_cleanup is None or now - self._last_cleanup >= CLEANUP_INTERVAL:
            self.cleanup()

    def cleanup(self) -> list[int]:
        """Hourly maintenance: retention rules, then missing channel artwork."""
        self._last_cleanup = utcnow()
        with self._sessions() as db:
            deleted = run_cleanup(db, self._settings.media_dir)
        for video_id in deleted:
            self._events.publish("video.deleted", video_id=video_id)
        try:
            with self._sessions() as db:
                if refresh_channel_artwork(db, self._catalog, self._settings.media_dir):
                    self._events.publish("channels.updated")
        except Exception:
            log.exception("Kanalbilder konnten nicht aktualisiert werden")
        return deleted
