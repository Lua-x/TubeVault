"""Classification of download errors into retryable and permanent kinds."""

from __future__ import annotations

import socket
import ssl
from datetime import timedelta

from app.models import ErrorKind

_RATE_LIMIT = (
    "http error 429",
    "too many requests",
    "rate-limit",
    "rate limit",
    "sign in to confirm you're not a bot",
    "sign in to confirm you’re not a bot",
)
_UNAVAILABLE = (
    "video unavailable",
    "private video",
    "this video is private",
    "has been removed",
    "has been terminated",
    "no longer available",
    "account associated with this video",
    "copyright",
    "not available in your country",
    "blocked it in your country",
    "members-only",
    "join this channel",
    "sign in to confirm your age",
    "age-restricted",
    "inappropriate for some users",
    "does not exist",
    "incomplete youtube id",
    "unsupported url",
    "is not a valid url",
    "http error 404",
    "http error 410",
)
_LIVE = (
    "premieres in",
    "live event will begin",
    "this live event",
    "is_upcoming",
    "livestream has not",
    "is currently live",
)
_NETWORK = (
    "unable to download webpage",
    "unable to download api page",
    "connection reset",
    "connection refused",
    "connection aborted",
    "timed out",
    "timeout",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
    "remote end closed connection",
    "incompleteread",
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "got error:",
    "ssl:",
    "giving up after",
)


class LiveContentError(Exception):
    """Raised for livestreams that are still running or have not started yet."""


def classify_error(exc: BaseException) -> ErrorKind:
    if isinstance(exc, LiveContentError):
        return ErrorKind.LIVE
    message = str(exc).lower()
    if any(s in message for s in _RATE_LIMIT):
        return ErrorKind.RATE_LIMITED
    if any(s in message for s in _LIVE):
        return ErrorKind.LIVE
    if any(s in message for s in _UNAVAILABLE):
        return ErrorKind.UNAVAILABLE
    if isinstance(exc, (ConnectionError, TimeoutError, socket.gaierror, ssl.SSLError)) or any(
        s in message for s in _NETWORK
    ):
        return ErrorKind.NETWORK
    return ErrorKind.UNKNOWN


def is_retryable(kind: ErrorKind) -> bool:
    return kind is not ErrorKind.UNAVAILABLE


def retry_delay(kind: ErrorKind, attempt: int) -> timedelta:
    """Exponential backoff. Rate limits back off much longer than network hiccups."""
    exponent = max(attempt - 1, 0)
    if kind is ErrorKind.LIVE:
        # Premieres and running streams: check again much later.
        return timedelta(seconds=min(30 * 60 * 2**exponent, 6 * 3600))
    if kind is ErrorKind.RATE_LIMITED:
        return timedelta(seconds=min(15 * 60 * 2**exponent, 6 * 3600))
    return timedelta(seconds=min(30 * 2**exponent, 3600))


def clean_message(exc: BaseException) -> str:
    """yt-dlp prefixes errors with 'ERROR: [youtube] id:'; keep the human part."""
    message = str(exc).strip() or exc.__class__.__name__
    if message.startswith("ERROR: "):
        message = message[len("ERROR: ") :]
    return message[:2000]
