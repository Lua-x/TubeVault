"""Objects shared across the application, stored on `app.state.ctx`."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.services.auth import LoginThrottle
from app.workers.download_manager import DownloadManager


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    events: EventBus
    downloads: DownloadManager
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
