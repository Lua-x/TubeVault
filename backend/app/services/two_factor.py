"""Two-factor login: setup, codes, recovery codes and the short-lived login tickets."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import totp
from app.models import User

TICKET_TTL = 300.0
TICKET_ATTEMPTS = 5


class TwoFactorError(Exception):
    """The message is shown to the user (German)."""


def begin_setup(db: Session, user: User) -> tuple[str, str]:
    """A new secret; it only takes effect once a code from the app was confirmed."""
    if user.two_factor:
        raise TwoFactorError("Die Zwei-Faktor-Anmeldung ist bereits eingeschaltet.")
    user.totp_secret = totp.new_secret()
    user.totp_enabled_at = None
    db.commit()
    return user.totp_secret, totp.otpauth_uri(user.totp_secret, user.username)


def _new_recovery_codes(user: User) -> list[str]:
    codes = totp.new_recovery_codes()
    user.recovery_codes = [totp.hash_recovery_code(code) for code in codes]
    return codes


def enable(db: Session, user: User, code: str) -> list[str]:
    if user.two_factor:
        raise TwoFactorError("Die Zwei-Faktor-Anmeldung ist bereits eingeschaltet.")
    if not user.totp_secret:
        raise TwoFactorError("Bitte die Einrichtung neu starten.")
    counter = totp.verify(user.totp_secret, code)
    if counter is None:
        raise TwoFactorError("Der Code stimmt nicht. Uhrzeit von Handy und Server prüfen.")
    user.totp_enabled_at = datetime.now(UTC)
    user.totp_last_counter = counter
    codes = _new_recovery_codes(user)
    db.commit()
    return codes


def check_code(db: Session, user: User, code: str) -> bool:
    """A code from the app or an unused recovery code (which is then used up)."""
    if not user.two_factor or not user.totp_secret:
        return False
    counter = totp.verify(user.totp_secret, code, last_counter=user.totp_last_counter)
    if counter is not None:
        user.totp_last_counter = counter
        db.commit()
        return True
    hashed = totp.hash_recovery_code(code)
    if len(totp.normalize_recovery_code(code)) == 10 and hashed in (user.recovery_codes or []):
        user.recovery_codes = [h for h in user.recovery_codes if h != hashed]
        db.commit()
        return True
    return False


def regenerate_recovery_codes(db: Session, user: User) -> list[str]:
    codes = _new_recovery_codes(user)
    db.commit()
    return codes


def disable(db: Session, user: User) -> None:
    user.totp_secret = None
    user.totp_enabled_at = None
    user.totp_last_counter = None
    user.recovery_codes = []
    db.commit()


@dataclass(slots=True)
class _Ticket:
    user_id: int
    expires: float
    attempts: int = 0


class LoginTickets:
    """After the right password: a ticket for entering the code, so the password is not
    sent twice. Kept in memory only; a restart simply means logging in again."""

    def __init__(self) -> None:
        self._tickets: dict[str, _Ticket] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: int) -> str:
        ticket = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._tickets = {k: t for k, t in self._tickets.items() if t.expires > now}
            self._tickets[ticket] = _Ticket(user_id, now + TICKET_TTL)
        return ticket

    def user_for(self, ticket: str) -> int | None:
        """The user of a valid ticket; counts the attempt."""
        with self._lock:
            entry = self._tickets.get(ticket)
            if entry is None or entry.expires < time.monotonic():
                self._tickets.pop(ticket, None)
                return None
            entry.attempts += 1
            if entry.attempts > TICKET_ATTEMPTS:
                self._tickets.pop(ticket, None)
                return None
            return entry.user_id

    def consume(self, ticket: str) -> None:
        with self._lock:
            self._tickets.pop(ticket, None)
