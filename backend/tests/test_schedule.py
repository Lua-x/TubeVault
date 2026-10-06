"""Subscriptions can be checked on chosen weekdays at a set local time."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.models import Subscription
from app.services.schedule import local_zone, next_scheduled, parse_time
from tests.conftest import FakeCatalog, FakeFeeds
from tests.test_rss import _setup
from tests.test_subscriptions import entry, subscribe, wait_checked

BERLIN = ZoneInfo("Europe/Berlin")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
SETTINGS = (
    "enabled", "check_interval_minutes", "check_days", "check_time", "include_shorts",
    "include_live", "min_duration_s", "max_duration_s", "date_after", "keep_days", "keep_last",
    "download_options",
)  # fmt: skip


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


def when(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def settings(sub: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {key: sub[key] for key in SETTINGS} | changes


def test_next_scheduled_day_and_time() -> None:
    monday_noon = utc(2026, 10, 5, 10, 0)  # 12:00 in Berlin (summer time, UTC+2)
    assert next_scheduled([MON, WED, FRI], "18:00", monday_noon, BERLIN) == utc(2026, 10, 5, 16)
    # Past today's time: the next chosen day.
    evening = utc(2026, 10, 5, 17, 0)
    assert next_scheduled([MON, WED, FRI], "18:00", evening, BERLIN) == utc(2026, 10, 7, 16)
    # Exactly at the time: not again right away, but a week later.
    assert next_scheduled([MON], "18:00", utc(2026, 10, 5, 16), BERLIN) == utc(2026, 10, 12, 16)
    # Only Sunday, from late Sunday evening.
    sunday_night = utc(2026, 10, 11, 21, 0)  # 23:00 in Berlin
    assert next_scheduled([SUN], "06:30", sunday_night, BERLIN) == utc(2026, 10, 18, 4, 30)
    with pytest.raises(ValueError):
        next_scheduled([], "06:30", sunday_night, BERLIN)
    with pytest.raises(ValueError):
        parse_time("24:00")


def test_next_scheduled_follows_the_wall_clock_across_dst() -> None:
    # Summer time ends on 25 Oct 2026: 18:00 in Berlin is 16:00 UTC before and 17:00 after.
    first = next_scheduled(range(7), "18:00", utc(2026, 10, 24, 12), BERLIN)
    second = next_scheduled(range(7), "18:00", first, BERLIN)
    assert (first, second) == (utc(2026, 10, 24, 16), utc(2026, 10, 25, 17))
    # 02:30 doesn't exist on 28 Mar 2027 (2:00 jumps to 3:00) – it still gives that day.
    moment = next_scheduled([SUN], "02:30", utc(2027, 3, 27, 12), BERLIN)
    assert moment.astimezone(BERLIN).date() == date(2027, 3, 28)


def test_schedule_through_the_api(admin: TestClient, catalog: FakeCatalog) -> None:
    catalog.entries = [entry(1)]
    created = subscribe(admin, check_days=[FRI, MON, FRI], check_time="18:30")
    assert (created["check_days"], created["check_time"]) == ([MON, FRI], "18:30")
    # The first check runs right away, the next on a Monday or Friday at 18:30.
    sub = wait_checked(admin, created["id"])
    local = when(sub["next_check_at"]).astimezone(local_zone())
    assert local.weekday() in (MON, FRI)
    assert (local.hour, local.minute) == (18, 30)
    assert when(sub["next_check_at"]) > when(sub["last_checked_at"])

    # Back to an interval: counted from the last check.
    url = f"/api/subscriptions/{sub['id']}"
    back = admin.put(url, json=settings(sub, check_days=None, check_interval_minutes=60)).json()
    assert (back["check_days"], back["check_time"]) == (None, None)
    assert when(back["next_check_at"]) - when(back["last_checked_at"]) == timedelta(minutes=60)

    # And to a schedule again: from now on.
    again = admin.put(url, json=settings(back, check_days=[SUN], check_time="07:00")).json()
    local = when(again["next_check_at"]).astimezone(local_zone())
    assert (local.weekday(), local.hour, local.minute) == (SUN, 7, 0)
    assert when(again["next_check_at"]) > datetime.now(UTC)


@pytest.mark.parametrize(
    "body",
    [
        {"check_days": [MON]},  # no time
        {"check_days": [7], "check_time": "08:00"},
        {"check_days": [MON], "check_time": "8 Uhr"},
    ],
)
def test_invalid_schedules(admin: TestClient, body: dict[str, Any]) -> None:
    assert admin.post("/api/subscriptions", json={"url": "@test", **body}).status_code == 422


def test_the_feed_does_not_move_a_schedule(
    admin: TestClient, catalog: FakeCatalog, feeds: FakeFeeds
) -> None:
    watcher, sub_id, url = _setup(admin, catalog, feeds)
    later = datetime.now(UTC) + timedelta(days=3)
    with admin.app.state.ctx.sessions() as db:  # type: ignore[attr-defined]
        sub = db.get(Subscription, sub_id)
        sub.check_days, sub.check_time, sub.next_check_at = [MON], "06:00", later
        db.commit()
    feeds.ids[url] = ["vid00000001", "vid00000002", "vid00000003"]  # a new upload
    assert watcher.run_round() == []
    with admin.app.state.ctx.sessions() as db:  # type: ignore[attr-defined]
        assert db.get(Subscription, sub_id).next_check_at.replace(tzinfo=UTC) == later
