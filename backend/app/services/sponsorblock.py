"""SponsorBlock: community-submitted segments (sponsors, intros, …) for YouTube videos.

Lookups use the privacy-preserving hash-prefix API: only the first four characters of the
SHA-256 of the video ID are sent, so SponsorBlock does not learn which video is watched.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import SponsorSegment, Video

log = logging.getLogger(__name__)

API_URL = "https://sponsor.ajay.app"
CATEGORIES = (
    "sponsor",
    "selfpromo",
    "interaction",
    "intro",
    "outro",
    "preview",
    "music_offtopic",
    "filler",
)
DEFAULT_CATEGORIES = ["sponsor", "selfpromo", "interaction"]
TIMEOUT = 10
# New videos get segments over the first days; refresh those more often.
REFRESH_RECENT = timedelta(hours=12)
REFRESH_OLD = timedelta(days=30)
RECENT_UPLOAD = timedelta(days=14)


@dataclass(frozen=True, slots=True)
class Segment:
    uuid: str
    category: str
    action: str
    start_s: float
    end_s: float


def parse_response(payload: Any, youtube_id: str, categories: list[str]) -> list[Segment]:
    segments: list[Segment] = []
    if not isinstance(payload, list):
        return segments
    for entry in payload:
        if not isinstance(entry, dict) or entry.get("videoID") != youtube_id:
            continue
        for raw in entry.get("segments") or []:
            try:
                start, end = (float(x) for x in raw["segment"])
                category = str(raw["category"])
                action = str(raw.get("actionType") or "skip")
                uuid = str(raw.get("UUID") or f"{category}-{start}")
            except (KeyError, TypeError, ValueError):
                continue
            if category in categories and action in ("skip", "mute") and end > start:
                segments.append(Segment(uuid, category, action, start, end))
    return sorted(segments, key=lambda s: s.start_s)


def fetch_segments(youtube_id: str, categories: list[str]) -> list[Segment]:
    prefix = hashlib.sha256(youtube_id.encode()).hexdigest()[:4]
    query = urllib.parse.urlencode(
        {"categories": json.dumps(categories), "actionTypes": json.dumps(["skip", "mute"])}
    )
    request = urllib.request.Request(  # noqa: S310 – fixed https URL
        f"{API_URL}/api/skipSegments/{prefix}?{query}",
        headers={"User-Agent": "TubeVault", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # no segments for any video with this prefix
            return []
        raise
    return parse_response(payload, youtube_id, categories)


def store_segments(db: Session, video: Video, segments: list[Segment]) -> None:
    video.sponsor_segments.clear()
    db.flush()
    for segment in segments:
        video.sponsor_segments.append(
            SponsorSegment(
                uuid=segment.uuid,
                category=segment.category,
                action=segment.action,
                start_s=segment.start_s,
                end_s=segment.end_s,
            )
        )
    video.sponsorblock_fetched_at = datetime.now(UTC)


def is_stale(video: Video, now: datetime | None = None) -> bool:
    if video.sponsorblock_cut:
        return False
    if video.sponsorblock_fetched_at is None:
        return True
    now = now or datetime.now(UTC)
    recent = video.upload_date and now.date() - video.upload_date <= RECENT_UPLOAD
    age = now - video.sponsorblock_fetched_at
    return age > (REFRESH_RECENT if recent else REFRESH_OLD)


def refresh(db: Session, video: Video, categories: list[str]) -> bool:
    """Fetch and store segments. Returns False if SponsorBlock could not be reached."""
    try:
        segments = fetch_segments(video.youtube_id, categories)
    except Exception as exc:
        log.info("SponsorBlock nicht erreichbar für %s: %s", video.youtube_id, exc)
        return False
    store_segments(db, video, segments)
    db.commit()
    return True
