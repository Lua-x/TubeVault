"""The RSS feed only moves the full check forward; it never queues anything itself."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import Subscription, SubscriptionKind
from app.services.rss import RssWatcher, feed_url, video_ids
from tests.conftest import FakeCatalog, FakeFeeds, FakeNetwork, wait_for
from tests.test_subscriptions import detail, entry, subscribe

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <entry><id>yt:video:abcdefghijk</id><yt:videoId>abcdefghijk</yt:videoId></entry>
 <entry><id>yt:video:A-b_c1234567</id><yt:videoId>A-b_c123456</yt:videoId></entry>
 <entry><yt:videoId>abcdefghijk</yt:videoId></entry>
</feed>"""


def test_feed_parsing() -> None:
    assert video_ids(FEED) == ["abcdefghijk", "A-b_c123456"]
    assert video_ids("<html>not a feed</html>") == []
    assert feed_url(SubscriptionKind.CHANNEL, "UCabc").endswith("?channel_id=UCabc")
    assert feed_url(SubscriptionKind.PLAYLIST, "PLx").endswith("?playlist_id=PLx")


def _setup(
    admin: TestClient, catalog: FakeCatalog, feeds: FakeFeeds
) -> tuple[RssWatcher, int, str]:
    catalog.entries = [entry(2), entry(3)]
    sub = subscribe(admin, backfill=2)
    wait_for(lambda: detail(admin, sub["id"])["last_checked_at"])
    ctx = admin.app.state.ctx  # type: ignore[attr-defined]
    wait_for(lambda: not ctx.checker.is_checking(sub["id"]))
    url = feed_url(SubscriptionKind.CHANNEL, FakeCatalog.CHANNEL_ID)
    watcher = RssWatcher(ctx.sessions, ctx.connectivity, feeds.fetch, interval=timedelta(0))
    return watcher, sub["id"], url


def _next_check(admin: TestClient, sub_id: int) -> datetime:
    with admin.app.state.ctx.sessions() as db:  # type: ignore[attr-defined]
        return db.get(Subscription, sub_id).next_check_at.replace(tzinfo=UTC)


def test_new_upload_moves_the_check_forward(
    admin: TestClient, catalog: FakeCatalog, feeds: FakeFeeds
) -> None:
    watcher, sub_id, url = _setup(admin, catalog, feeds)
    feeds.ids[url] = ["vid00000002", "vid00000003"]
    assert watcher.run_round() == []  # nothing new
    assert _next_check(admin, sub_id) > datetime.now(UTC) + timedelta(hours=1)

    catalog.entries = [entry(1), entry(2), entry(3)]
    feeds.ids[url] = ["vid00000001", "vid00000002", "vid00000003"]
    assert watcher.run_round() == [sub_id]
    assert _next_check(admin, sub_id) <= datetime.now(UTC)
    # The scheduler then runs the full check, which queues the new video.
    admin.app.state.ctx.scheduler.wake()  # type: ignore[attr-defined]
    wait_for(
        lambda: (
            detail(admin, sub_id)["stats"]["queued"] + detail(admin, sub_id)["stats"]["downloaded"]
            == 3
        )
    )


def test_excluded_shorts_do_not_trigger_again_and_again(
    admin: TestClient, catalog: FakeCatalog, feeds: FakeFeeds
) -> None:
    watcher, sub_id, url = _setup(admin, catalog, feeds)
    # A Short in the feed: the full check lists only the videos tab, so it stays unknown.
    feeds.ids[url] = ["short000001", "vid00000002"]
    assert watcher.run_round() == [sub_id]
    with admin.app.state.ctx.sessions() as db:  # type: ignore[attr-defined]
        db.get(Subscription, sub_id).next_check_at = datetime.now(UTC) + timedelta(hours=6)
        db.commit()
    assert watcher.run_round() == []


def test_rss_can_be_turned_off_and_waits_offline(
    admin: TestClient, catalog: FakeCatalog, feeds: FakeFeeds, network: FakeNetwork
) -> None:
    watcher, _sub_id, url = _setup(admin, catalog, feeds)
    feeds.ids[url] = ["vid00000009"]
    body = admin.get("/api/settings").json()
    body["automation"]["rss"] = False
    assert admin.put("/api/settings", json=body).status_code == 200
    calls = len(feeds.calls)
    assert watcher.run_round() == [] and len(feeds.calls) == calls

    body["automation"]["rss"] = True
    admin.put("/api/settings", json=body)
    network.online = False
    admin.app.state.ctx.connectivity.confirm_offline()  # type: ignore[attr-defined]
    assert watcher.run_round() == [] and len(feeds.calls) == calls
