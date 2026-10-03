"""Is the internet (YouTube) reachable?

TubeVault is a media server for watching offline: everything except fetching new
videos must keep working without internet. This tracks the connection so online
features (downloads, subscription checks, SponsorBlock) wait quietly instead of
failing, timing out or flooding the log.

There is no polling: TubeVault only probes after a network error, and while offline
at most once per `recheck_s` when something wants to go online.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

PROBE_URL = "https://www.youtube.com/generate_204"
PROBE_TIMEOUT = 5.0


def probe_youtube() -> bool:
    """One small request to YouTube. Any HTTP answer means we are online."""
    request = urllib.request.Request(PROBE_URL, method="HEAD", headers={"User-Agent": "TubeVault"})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT):  # noqa: S310 – fixed https URL
            return True
    except urllib.error.HTTPError:
        return True
    except (OSError, ValueError):
        return False


class Connectivity:
    def __init__(
        self,
        probe: Callable[[], bool] = probe_youtube,
        recheck_s: float = 60.0,
        on_change: Callable[[bool], Any] | None = None,
    ) -> None:
        self._probe = probe
        self._recheck_s = recheck_s
        self.on_change = on_change
        self._lock = threading.Lock()
        self._online = True
        self._offline_since: datetime | None = None
        self._last_probe = 0.0

    @property
    def online(self) -> bool:
        return self._online

    @property
    def offline_since(self) -> datetime | None:
        return self._offline_since

    def _set(self, online: bool) -> None:
        changed = online != self._online
        self._online = online
        if not changed:
            return
        if online:
            log.info("Internet wieder erreichbar – Downloads und Abo-Prüfungen laufen weiter.")
            self._offline_since = None
        else:
            log.warning(
                "Keine Internetverbindung – die Bibliothek funktioniert weiter, "
                "Downloads und Abo-Prüfungen warten."
            )
            self._offline_since = datetime.now(UTC)
        if self.on_change:
            self.on_change(online)

    def _run_probe(self) -> bool:
        self._last_probe = time.monotonic()
        online = self._probe()
        self._set(online)
        return online

    def confirm_offline(self) -> bool:
        """After a network error: is the whole connection down (True) or was it a hiccup?"""
        with self._lock:
            if not self._online and time.monotonic() - self._last_probe < self._recheck_s:
                return True
            return not self._run_probe()

    def should_wait(self) -> bool:
        """Before going online: True while offline. Re-probes at most once per `recheck_s`."""
        if self._online:
            return False
        with self._lock:
            if self._online:
                return False
            if time.monotonic() - self._last_probe < self._recheck_s:
                return True
            return not self._run_probe()

    def report_success(self) -> None:
        """Something online just worked – we are back."""
        if not self._online:
            with self._lock:
                self._set(True)
