"""Objects shared across the application, stored on `app.state.ctx`."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.events import EventBus
from app.services.auth import LoginThrottle
from app.services.catalog import Catalog
from app.services.subscriptions import SubscriptionChecker
from app.workers.download_manager import DownloadManager
from app.workers.scheduler import SubscriptionScheduler
from app.workers.transcoder import Transcoder


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    events: EventBus
    downloads: DownloadManager
    catalog: Catalog
    checker: SubscriptionChecker
    scheduler: SubscriptionScheduler
    transcoder: Transcoder
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
