"""Push notifications to the admin's own services: ntfy, Gotify or any webhook.

Off by default, and TubeVault only ever talks to the address the admin entered (often
a server in the same network). Sending happens on a background thread, so downloads
never wait for it, and events are collected for a short while: a new subscription
that downloads 50 videos sends one "50 neue Videos" instead of 50 messages.

The access token is kept apart from the other settings and never sent back to the
browser, so only admins can set it and nobody can read it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.models import Setting

log = logging.getLogger(__name__)

Service = Literal["off", "ntfy", "gotify", "webhook"]
Event = Literal[
    "video_downloaded", "download_failed", "subscription_error", "ytdlp_update", "disk_low"
]

SETTINGS_KEY = "notifications"
SEND_TIMEOUT = 10
BATCH_WINDOW = 30.0
LISTED = 5  # titles named in a summary
ERROR_LOG_INTERVAL = 600.0


class NotificationEvents(BaseModel):
    video_downloaded: bool = True
    download_failed: bool = True
    subscription_error: bool = True
    ytdlp_update: bool = False
    disk_low: bool = True


class NotificationConfig(BaseModel):
    service: Service = "off"
    # ntfy: topic URL (https://ntfy.example.org/tubevault), Gotify: server URL, webhook: URL.
    url: str = Field(default="", max_length=1000)
    # ntfy access token (optional) or Gotify application token.
    token: str = Field(default="", max_length=500)
    events: NotificationEvents = Field(default_factory=NotificationEvents)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        if value:
            parts = urllib.parse.urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("Bitte eine Adresse mit http:// oder https:// angeben.")
        return value

    @property
    def active(self) -> bool:
        return self.service != "off" and bool(self.url)


def load_config(db: Session) -> NotificationConfig:
    row = db.get(Setting, SETTINGS_KEY)
    if row is None or not isinstance(row.value, dict):
        return NotificationConfig()
    try:
        return NotificationConfig.model_validate(row.value)
    except ValueError:
        log.warning("Benachrichtigungs-Einstellungen ungültig – zurückgesetzt")
        return NotificationConfig()


def save_config(db: Session, config: NotificationConfig) -> None:
    row = db.get(Setting, SETTINGS_KEY)
    value = config.model_dump(mode="json")
    if row is None:
        db.add(Setting(key=SETTINGS_KEY, value=value))
    else:
        row.value = value
    db.commit()


@dataclass(slots=True)
class Message:
    event: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


class NotifyError(Exception):
    """Sending failed; the message is meant for the admin (German)."""


TAGS = {
    "video_downloaded": ["tv"],
    "download_failed": ["warning"],
    "subscription_error": ["warning"],
    "ytdlp_update": ["arrow_up"],
    "disk_low": ["floppy_disk"],
    "test": ["white_check_mark"],
}


def build_request(config: NotificationConfig, message: Message) -> urllib.request.Request:
    headers = {"User-Agent": "TubeVault", "Content-Type": "application/json"}
    if config.service == "ntfy":
        # JSON publishing: UTF-8 titles work, no header encoding games.
        parts = urllib.parse.urlsplit(config.url.rstrip("/"))
        base, _, topic = parts.path.rpartition("/")
        if not topic:
            raise NotifyError("Bei ntfy gehört das Thema in die Adresse, z. B. …/tubevault.")
        url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, base or "/", "", ""))
        payload: dict[str, Any] = {
            "topic": topic,
            "title": message.title,
            "message": message.body,
            "tags": TAGS.get(message.event, []),
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
    elif config.service == "gotify":
        if not config.token:
            raise NotifyError("Für Gotify braucht es den Token einer Anwendung.")
        url = f"{config.url.rstrip('/')}/message"
        payload = {"title": message.title, "message": message.body, "priority": 5}
        headers["X-Gotify-Key"] = config.token
    elif config.service == "webhook":
        url = config.url
        payload = {
            "event": message.event,
            "title": message.title,
            "message": message.body,
            "data": message.data,
            "sent_at": datetime.now(UTC).isoformat(),
        }
    else:
        raise NotifyError("Keine Benachrichtigungen eingerichtet.")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310


def send(config: NotificationConfig, message: Message) -> None:
    request = build_request(config, message)
    try:
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT):  # noqa: S310 – admin's own URL
            return
    except urllib.error.HTTPError as exc:
        hint = " – Token prüfen" if exc.code in (401, 403) else ""
        raise NotifyError(f"Der Dienst antwortet mit Fehler {exc.code}{hint}.") from exc
    except (OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NotifyError(f"Nicht erreichbar: {reason}") from exc


def summarize(event: str, messages: list[Message]) -> Message:
    """One message for everything of one kind that came in during the window."""
    if len(messages) == 1:
        return messages[0]
    count = len(messages)
    titles = {
        "video_downloaded": f"{count} neue Videos",
        "download_failed": f"{count} Downloads fehlgeschlagen",
        "subscription_error": f"{count} Abo-Prüfungen fehlgeschlagen",
    }
    lines = [f"• {m.data.get('name') or m.body.splitlines()[0]}" for m in messages[:LISTED]]
    if count > LISTED:
        lines.append(f"… und {count - LISTED} weitere")
    return Message(
        event=event,
        title=titles.get(event, messages[0].title),
        body="\n".join(lines),
        data={"count": count, "items": [m.data for m in messages]},
    )


Sender = Callable[[NotificationConfig, Message], None]


class Notifier:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        sender: Sender = send,
        window: float = BATCH_WINDOW,
    ) -> None:
        self._sessions = sessions
        self._send = sender
        self._window = window
        self._lock = threading.Lock()
        self._pending: dict[str, list[Message]] = {}
        self._due: dict[str, float] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error_log = 0.0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="notifications", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def config(self) -> NotificationConfig:
        with self._sessions() as db:
            return load_config(db)

    def notify(self, event: Event, title: str, body: str, **data: Any) -> None:
        """Queue a message if notifications are on and this event is wanted."""
        try:
            config = self.config()
        except Exception:
            log.exception("Benachrichtigungs-Einstellungen nicht lesbar")
            return
        if not config.active or not getattr(config.events, event):
            return
        with self._lock:
            self._pending.setdefault(event, []).append(Message(event, title, body, data))
            self._due.setdefault(event, time.monotonic() + self._window)
        self._wake.set()

    def flush(self, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            ready = [e for e, due in self._due.items() if force or due <= now]
            batches = [(e, self._pending.pop(e, [])) for e in ready]
            for event in ready:
                self._due.pop(event, None)
        if not batches:
            return
        config = self.config()
        if not config.active:
            return
        for event, messages in batches:
            if not messages:
                continue
            try:
                self._send(config, summarize(event, messages))
            except NotifyError as exc:
                if time.monotonic() - self._last_error_log > ERROR_LOG_INTERVAL:
                    self._last_error_log = time.monotonic()
                    log.warning("Benachrichtigung nicht gesendet: %s", exc)

    def test(self, config: NotificationConfig) -> None:
        """Send a test message right away; raises NotifyError with the reason."""
        self._send(
            config,
            Message(
                "test",
                "TubeVault",
                "Benachrichtigungen funktionieren. 🎉",
                {"test": True},
            ),
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                next_due = min(self._due.values(), default=None)
            timeout = None if next_due is None else max(next_due - time.monotonic(), 0.0)
            self._wake.wait(timeout)
            self._wake.clear()
            try:
                self.flush(force=self._stop.is_set())
            except Exception:
                log.exception("Fehler beim Senden von Benachrichtigungen")
