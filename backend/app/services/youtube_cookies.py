"""YouTube cookies for videos that need a signed-in account: age-restricted, members-only
and private ones.

The admin uploads a cookies.txt (Netscape format, as browser add-ons export it). Only the
cookies of youtube.com and google.com are kept. They live in /config/cookies, readable
only by TubeVault – not in the database, so never in a backup – and their values are
never logged or sent back to the browser.

Requests go out without them first; only when YouTube asks for a sign-in is one repeated
with the cookies (`downloader.with_login`). yt-dlp works on a copy, and what YouTube
refreshes on the way is written back, unless new cookies were uploaded meanwhile.
Cookies that expired – by their date, or because YouTube signed them out – are reported
once: in the admin area and as a notification.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.services.notifications import Notifier

log = logging.getLogger(__name__)

MAX_BYTES = 1024**2
DOMAINS = ("youtube.com", "google.com")
# Signed in, the way yt-dlp checks it: LOGIN_INFO plus one of the SAPISID cookies.
LOGIN_INFO = "LOGIN_INFO"
SAPISID = ("SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID")
HTTPONLY_PREFIX = "#HttpOnly_"
HEADER = "# Netscape HTTP Cookie File\n# Saved by TubeVault: only youtube.com and google.com.\n\n"

Problem = Literal["expired", "rejected"]


class CookieError(Exception):
    """The upload is no usable cookies.txt – the message says why (German)."""


@dataclass(frozen=True, slots=True)
class Cookie:
    domain: str  # without the leading dot
    name: str
    expires: int  # Unix time, 0 for a session cookie
    line: str  # as in the file


@dataclass(frozen=True, slots=True)
class CookieStatus:
    stored: bool
    count: int = 0
    uploaded_at: datetime | None = None
    # The first login cookie to run out; None when they last as long as the browser session.
    expires_at: datetime | None = None
    used_at: datetime | None = None  # last time a video needed them, and they worked
    problem: Problem | None = None


def parse(text: str) -> list[Cookie]:
    """The cookies in a Netscape cookies.txt; lines that are none are skipped."""
    cookies: list[Cookie] = []
    for raw in text.lstrip("﻿").splitlines():
        line = raw.rstrip("\r")
        if line.startswith(HTTPONLY_PREFIX):
            body = line[len(HTTPONLY_PREFIX) :]
        elif line.startswith("#") or not line.strip():
            continue
        else:
            body = line
        fields = body.split("\t")
        if len(fields) != 7:
            continue
        domain, _, _, _, expires, name, _ = fields
        try:
            expiry = int(float(expires or 0))
        except ValueError:
            continue
        cookies.append(Cookie(domain.strip().lower().lstrip("."), name, max(expiry, 0), line))
    return cookies


def _ours(cookie: Cookie) -> bool:
    return any(cookie.domain == d or cookie.domain.endswith(f".{d}") for d in DOMAINS)


def _youtube(cookies: list[Cookie]) -> dict[str, Cookie]:
    return {
        c.name: c for c in cookies if c.domain == "youtube.com" or c.domain.endswith(".youtube.com")
    }


def signed_in(cookies: list[Cookie]) -> bool:
    youtube = _youtube(cookies)
    return LOGIN_INFO in youtube and any(name in youtube for name in SAPISID)


def expires_at(cookies: list[Cookie]) -> datetime | None:
    youtube = _youtube(cookies)
    dates = [c.expires for name in (LOGIN_INFO, *SAPISID) if (c := youtube.get(name)) and c.expires]
    return datetime.fromtimestamp(min(dates), UTC) if dates else None


def _content(cookies: list[Cookie]) -> str:
    return HEADER + "".join(f"{c.line}\n" for c in cookies)


def _now() -> datetime:
    return datetime.now(UTC)


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


class YouTubeCookies:
    def __init__(self, folder: Path, notifier: Notifier | None = None) -> None:
        self._folder = folder
        self._notifier = notifier
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._folder / "youtube.txt"

    @property
    def _state_path(self) -> Path:
        return self._folder / "state.json"

    # --- what the admin does --------------------------------------------------------

    def save(self, data: bytes) -> CookieStatus:
        """Check an uploaded cookies.txt and store what TubeVault needs of it."""
        if len(data) > MAX_BYTES:
            raise CookieError("Die Datei ist zu groß für eine cookies.txt.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CookieError("Das ist keine Textdatei. Bitte eine cookies.txt wählen.") from exc
        cookies = [c for c in parse(text) if _ours(c)]
        if not cookies:
            hint = " (Netscape-Format)" if text.lstrip().startswith(("[", "{")) else ""
            raise CookieError(
                f"In der Datei stehen keine YouTube-Cookies. Bitte als cookies.txt{hint} "
                "exportieren, während youtube.com geöffnet ist."
            )
        if not signed_in(cookies):
            raise CookieError(
                "In den Cookies steckt keine Anmeldung bei YouTube. Erst auf youtube.com "
                "anmelden, dann exportieren."
            )
        expiry = expires_at(cookies)
        if expiry is not None and expiry <= _now():
            raise CookieError("Diese Cookies sind schon abgelaufen. Bitte neu exportieren.")
        with self._lock:
            self._write(cookies)
            self._save_state({"uploaded_at": _now().isoformat()})
        log.info("YouTube-Cookies hinterlegt (%d Cookies)", len(cookies))
        return self.status()

    def remove(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)
            self._state_path.unlink(missing_ok=True)
        log.info("YouTube-Cookies entfernt")

    def status(self) -> CookieStatus:
        with self._lock:
            cookies = self._read()
            state = self._state()
        if cookies is None:
            return CookieStatus(stored=False)
        expiry = expires_at(cookies)
        problem: Problem | None = None
        if state.get("rejected_at") or not signed_in(cookies):
            problem = "rejected"
        elif expiry is not None and expiry <= _now():
            problem = "expired"
        return CookieStatus(
            stored=True,
            count=len(cookies),
            uploaded_at=_time(state.get("uploaded_at")),
            expires_at=expiry,
            used_at=_time(state.get("used_at")),
            problem=problem,
        )

    # --- what the downloads do --------------------------------------------------------

    def usable(self) -> bool:
        status = self.status()
        return status.stored and status.problem is None

    @contextmanager
    def lend(self) -> Iterator[Path]:
        """A private copy for one yt-dlp run; what YouTube refreshed is taken back after."""
        with self._lock:
            original = self.path.read_bytes()
        work = self._folder / "tmp"
        work.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=work, suffix=".txt")
        copy = Path(name)
        try:
            with os.fdopen(handle, "wb") as target:
                target.write(original)
        except OSError:
            copy.unlink(missing_ok=True)
            raise
        try:
            yield copy
        finally:
            # Also after a failed run: that is when YouTube may have signed them out.
            try:
                self._take_back(original, copy)
            except Exception:
                log.exception("Erneuerte YouTube-Cookies nicht übernommen")
            copy.unlink(missing_ok=True)

    def used(self) -> None:
        with self._lock:
            if not self.path.is_file():
                return
            state = self._state()
            state["used_at"] = _now().isoformat()
            self._save_state(state)

    def check(self) -> None:
        """Report a problem once – hourly from the scheduler, and right when one is found."""
        status = self.status()
        if not status.stored or status.problem is None:
            return
        with self._lock:
            state = self._state()
            if state.get("notified") or not self.path.is_file():
                return
            state["notified"] = True
            self._save_state(state)
        if status.problem == "rejected":
            log.warning("YouTube nimmt die hinterlegten Cookies nicht mehr an")
            reason = "YouTube hat die Anmeldung beendet."
        else:
            log.warning("Die hinterlegten YouTube-Cookies sind abgelaufen")
            reason = "Die YouTube-Cookies sind abgelaufen."
        if self._notifier is not None:
            self._notifier.notify(
                "cookies_expired",
                "YouTube-Cookies abgelaufen",
                f"{reason} Videos ab 18, für Mitglieder oder private Videos lassen sich erst "
                "wieder laden, wenn du unter Verwaltung → YouTube-Anmeldung neue hochlädst.",
                problem=status.problem,
            )

    def hint(self) -> str:
        """What a download that needs a sign-in tells the admin (German)."""
        status = self.status()
        if not status.stored:
            return (
                "YouTube verlangt eine Anmeldung. Unter Verwaltung → YouTube-Anmeldung lassen "
                "sich dafür Cookies hinterlegen."
            )
        return (
            "YouTube verlangt eine Anmeldung, die hinterlegten Cookies sind aber abgelaufen. "
            "Bitte unter Verwaltung → YouTube-Anmeldung neue hochladen."
        )

    # --- files ----------------------------------------------------------------------------

    def _take_back(self, original: bytes, copy: Path) -> None:
        try:
            text = copy.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        cookies = [c for c in parse(text) if _ours(c)]
        if not signed_in(cookies):
            # YouTube signed these cookies out (yt-dlp warns about it, too). The upload
            # stays as it was; the admin needs new ones either way.
            with self._lock:
                if not self.path.is_file() or self.path.read_bytes() != original:
                    return  # new ones were uploaded in the meantime
                state = self._state()
                state["rejected_at"] = _now().isoformat()
                self._save_state(state)
            self.check()
            return
        content = _content(cookies)
        with self._lock:
            if not self.path.is_file() or self.path.read_bytes() != original:
                return  # replaced or removed in the meantime
            if content.encode("utf-8") != original:
                self._replace(self.path, content)

    def _read(self) -> list[Cookie] | None:
        try:
            return parse(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError):
            log.warning("YouTube-Cookies nicht lesbar")
            return []

    def _write(self, cookies: list[Cookie]) -> None:
        self._replace(self.path, _content(cookies))

    def _state(self) -> dict[str, Any]:
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self._replace(self._state_path, json.dumps(state))

    def _replace(self, path: Path, text: str) -> None:
        """Written next to the target and moved over it, readable only by TubeVault."""
        self._folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=self._folder, suffix=".part")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as target:
                target.write(text)
            os.replace(name, path)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(name)
