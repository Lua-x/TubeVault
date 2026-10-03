"""Checks subscriptions when they are due and runs the cleanup regularly."""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.models import Subscription
from app.services.app_settings import load_app_settings
from app.services.backups import BackupError, auto_backup_if_due
from app.services.catalog import Catalog
from app.services.connectivity import Connectivity
from app.services.notifications import Notifier
from app.services.rss import RssWatcher
from app.services.subscriptions import (
    SubscriptionChecker,
    refresh_channel_artwork,
    run_cleanup,
)
from app.services.ytdlp_updater import (
    _version_key,
    current_ytdlp_version,
    latest_ytdlp_version,
)

log = logging.getLogger(__name__)

CLEANUP_INTERVAL = timedelta(hours=1)
DISK_LOW_BYTES = 5 * 1024**3
DISK_LOW_SHARE = 0.05
YTDLP_CHECK_INTERVAL = timedelta(days=1)
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
        connectivity: Connectivity | None = None,
        rss: RssWatcher | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._disk_warned = False
        self._ytdlp_checked: datetime | None = None
        self._ytdlp_notified: str | None = None
        self._connectivity = connectivity
        self._rss = rss
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
                if self._rss and self._rss.run_round():
                    self._run_due()  # new uploads: check those subscriptions right away
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
        self._auto_backup()
        self._check_disk()
        self._check_ytdlp()
        if self._connectivity and not self._connectivity.online:
            return deleted  # channel artwork comes from YouTube; try again next hour
        try:
            with self._sessions() as db:
                if refresh_channel_artwork(db, self._catalog, self._settings.media_dir):
                    self._events.publish("channels.updated")
        except Exception:
            log.exception("Kanalbilder konnten nicht aktualisiert werden")
        return deleted

    def _auto_backup(self) -> None:
        with self._sessions() as db:
            options = load_app_settings(db).backup
        if not options.auto:
            return
        try:
            auto_backup_if_due(self._settings, options.keep)
        except BackupError:
            log.exception("Automatische Sicherung fehlgeschlagen")

    def _check_disk(self) -> None:
        """Warn once when /media runs low; again only after space was freed in between."""
        if self._notifier is None:
            return
        try:
            usage = shutil.disk_usage(self._settings.media_dir)
        except OSError:
            return
        low = usage.free < DISK_LOW_BYTES or usage.free < usage.total * DISK_LOW_SHARE
        if low and not self._disk_warned:
            self._disk_warned = True
            self._notifier.notify(
                "disk_low",
                "Speicherplatz wird knapp",
                f"Auf /media sind noch {usage.free / 1024**3:.1f} GB frei "
                f"({usage.free / usage.total:.0%}).",
                free=usage.free,
                total=usage.total,
            )
        elif usage.free > DISK_LOW_BYTES * 2 and usage.free > usage.total * DISK_LOW_SHARE * 2:
            self._disk_warned = False

    def _check_ytdlp(self) -> None:
        """Only when the admin wants to hear about yt-dlp updates: ask PyPI once a day."""
        if self._notifier is None:
            return
        now = utcnow()
        if self._ytdlp_checked and now - self._ytdlp_checked < YTDLP_CHECK_INTERVAL:
            return
        config = self._notifier.config()
        if not config.active or not config.events.ytdlp_update:
            return
        if self._connectivity and not self._connectivity.online:
            return
        self._ytdlp_checked = now
        latest = latest_ytdlp_version()
        installed = current_ytdlp_version()
        if (
            latest
            and installed
            and _version_key(latest) > _version_key(installed)
            and latest != self._ytdlp_notified
        ):
            self._ytdlp_notified = latest
            self._notifier.notify(
                "ytdlp_update",
                "yt-dlp-Update verfügbar",
                f"Version {latest} ist da (installiert: {installed}). "
                "Aktualisieren unter Verwaltung → yt-dlp.",
                latest=latest,
                installed=installed,
            )
