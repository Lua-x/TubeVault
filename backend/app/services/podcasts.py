"""Podcast feeds: a channel or playlist as RSS, for podcast apps in the home network.

Podcast apps can't sign in, so the address carries a per-user token instead. It only
reads feeds and their sound – nothing else – and can be renewed at any time.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import format_datetime
from pathlib import Path

from app.services.transcode import ProbeError, probe
from app.workers.transcoder import Source, TranscodeError, Transcoder

log = logging.getLogger(__name__)

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES)
# The newest episodes in a feed – and how many of them get their sound prepared ahead.
FEED_ITEMS = 100
PREFETCH = 10


def new_feed_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class FeedItem:
    guid: str
    title: str
    description: str
    link: str
    published: date | datetime | None
    audio_url: str
    audio_size: int
    duration: int | None
    image_url: str | None


@dataclass(frozen=True)
class Feed:
    title: str
    description: str
    link: str
    author: str
    image_url: str | None
    items: list[FeedItem]


def _rfc2822(value: date | datetime) -> str:
    moment = (
        value
        if isinstance(value, datetime)
        else datetime(value.year, value.month, value.day, 12, tzinfo=UTC)
    )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return format_datetime(moment)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = text
    return element


def render_feed(feed: Feed) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = _sub(rss, "channel")
    _sub(channel, "title", feed.title)
    _sub(channel, "link", feed.link)
    _sub(channel, "description", feed.description or feed.title)
    _sub(channel, "language", "de")
    _sub(channel, "generator", "TubeVault")
    _sub(channel, f"{{{ITUNES}}}author", feed.author)
    _sub(channel, f"{{{ITUNES}}}summary", feed.description or feed.title)
    # Private: podcast directories must not list it.
    _sub(channel, f"{{{ITUNES}}}block", "Yes")
    if feed.image_url:
        _sub(channel, f"{{{ITUNES}}}image", href=feed.image_url)
        image = _sub(channel, "image")
        _sub(image, "url", feed.image_url)
        _sub(image, "title", feed.title)
        _sub(image, "link", feed.link)
    for entry in feed.items:
        item = _sub(channel, "item")
        _sub(item, "title", entry.title)
        _sub(item, "link", entry.link)
        _sub(item, "guid", entry.guid, isPermaLink="false")
        _sub(item, "description", entry.description[:4000])
        if entry.published:
            _sub(item, "pubDate", _rfc2822(entry.published))
        _sub(
            item,
            "enclosure",
            url=entry.audio_url,
            length=str(entry.audio_size),
            type="audio/mp4",
        )
        if entry.duration:
            _sub(item, f"{{{ITUNES}}}duration", str(entry.duration))
        if entry.image_url:
            _sub(item, f"{{{ITUNES}}}image", href=entry.image_url)
    return bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))


class AudioPrefetch:
    """Prepares the sound of the newest episodes, one at a time, so apps get it at once."""

    def __init__(self, transcoder: Transcoder) -> None:
        self._transcoder = transcoder
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="podcast")
        self._lock = threading.Lock()
        self._pending: set[int] = set()

    def request(self, videos: list[tuple[int, Path]]) -> None:
        for video_id, path in videos[:PREFETCH]:
            if self._transcoder.cached_audio(video_id, path) is not None:
                continue
            with self._lock:
                if video_id in self._pending:
                    continue
                self._pending.add(video_id)
            self._executor.submit(self._run, video_id, path)

    def _run(self, video_id: int, path: Path) -> None:
        try:
            job = self._transcoder.audio(Source(video_id=video_id, path=path, info=probe(path)))
            wait_for(lambda: job.state != "running", timeout=1800)
        except (ProbeError, TranscodeError, OSError) as exc:
            log.info("Tonspur für Video %s nicht vorbereitet: %s", video_id, exc)
        finally:
            with self._lock:
                self._pending.discard(video_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def wait_for(done: Callable[[], bool], timeout: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while not done():
        if time.monotonic() > deadline:
            return False
        time.sleep(interval)
    return True
