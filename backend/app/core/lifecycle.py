"""Process lifecycle: uptime and restarting TubeVault from the UI.

A restart stops the web server gracefully (SIGTERM to ourselves) and then replaces the
process with a fresh one (see `app.__main__.serve`). The PID stays the same, so the
container keeps running, and a freshly installed yt-dlp is imported.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import Any

STARTED_AT = time.time()
_restart = threading.Event()
_server: Any = None


def register_server(server: Any) -> None:
    """The uvicorn server to stop for a restart (set by `app.__main__.serve`)."""
    global _server
    _server = server


def restart_requested() -> bool:
    return _restart.is_set()


def _stop() -> None:
    if _server is not None:
        # Graceful shutdown without a signal: uvicorn re-raises SIGTERM after shutting down,
        # which would end the process before it can restart itself.
        _server.should_exit = True
    else:
        os.kill(os.getpid(), signal.SIGTERM)


def request_restart(delay: float = 0.5) -> None:
    _restart.set()
    # Give the HTTP response a moment to leave before shutting down.
    threading.Timer(delay, _stop).start()


def uptime_s() -> float:
    return time.time() - STARTED_AT
