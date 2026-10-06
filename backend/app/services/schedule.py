"""When a subscription is checked: every N minutes, or on chosen weekdays at a set time.

Times are local – the container's TZ (e.g. Europe/Berlin), like the clock on the wall.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
_TIME = re.compile(TIME_PATTERN)


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; they are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def local_zone() -> tzinfo:
    name = os.environ.get("TZ", "").strip().lstrip(":")
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now().astimezone().tzinfo or UTC


def parse_time(value: str) -> time:
    if not _TIME.match(value):
        raise ValueError(f"Keine Uhrzeit: {value!r}")
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def next_scheduled(
    days: Iterable[int], at: str, after: datetime, zone: tzinfo | None = None
) -> datetime:
    """The first chosen weekday (0 = Monday) at the local time `at`, later than `after`."""
    wanted = set(days)
    if not wanted:
        raise ValueError("Kein Wochentag gewählt")
    zone = zone or local_zone()
    clock = parse_time(at)
    today = after.astimezone(zone).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if day.weekday() not in wanted:
            continue
        # Through UTC, so a time that doesn't exist on a DST day still gives a real moment.
        moment = datetime.combine(day, clock, tzinfo=zone).astimezone(UTC)
        if moment > after:
            return moment
    raise AssertionError("unreachable: a chosen weekday comes within 8 days")


def next_check(
    *,
    interval_minutes: int,
    days: list[int] | None,
    at: str | None,
    after: datetime,
) -> datetime:
    """When the next regular check is due, counted from `after` (a check or now)."""
    if days and at:
        return next_scheduled(days, at, after)
    return after + timedelta(minutes=interval_minutes)
