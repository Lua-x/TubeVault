"""DLNA/UPnP for TVs in the home network: device description, folders (Browse) and files.

DLNA has no logins. These routes therefore answer only while DLNA is switched on, only
to addresses of the home network and never through a reverse proxy, and they show what
the account chosen in the settings may see.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from xml.etree.ElementTree import ParseError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import Select, false, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import AppConfig, DbSession
from app.models import Channel, Playlist, PlaylistItem, User, Video, VideoStatus
from app.routers.media import VIDEO_MIME, _media_file
from app.services import dlna
from app.services.access import channel_filter, visible_videos
from app.services.app_settings import DlnaOptions, load_app_settings

router = APIRouter(prefix="/dlna", tags=["dlna"], include_in_schema=False)

XML_TYPE = 'text/xml; charset="utf-8"'
# Hard cap per Browse answer; clients page through bigger folders.
MAX_PAGE = 500
RECENT_COUNT = 100


@dataclass(frozen=True)
class DlnaAccess:
    options: DlnaOptions
    # None: every video, no playlists.
    user: User | None


def dlna_access(request: Request, db: DbSession) -> DlnaAccess:
    options = load_app_settings(db).dlna
    if not options.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    headers = request.headers
    # Behind a proxy every request looks local – and DLNA is meant for the LAN only.
    proxied = "x-forwarded-for" in headers or "forwarded" in headers or "x-real-ip" in headers
    if proxied or not dlna.is_home_network(request.client.host if request.client else None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur im Heimnetz")
    user = db.get(User, options.user_id) if options.user_id is not None else None
    if options.user_id is not None and user is None:
        # The chosen account is gone: show nothing rather than everything.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return DlnaAccess(options, user)


Access = Annotated[DlnaAccess, Depends(dlna_access)]


def _xml(body: bytes, status_code: int = 200) -> Response:
    return Response(body, status_code=status_code, media_type=XML_TYPE)


@router.get("/description.xml")
def description(access: Access, db: DbSession) -> Response:
    return _xml(dlna.device_description(access.options.name, dlna.device_udn(db)))


@router.get("/ContentDirectory.xml")
def content_directory_scpd(_: Access) -> Response:
    return _xml(dlna.CONTENT_DIRECTORY_SCPD)


@router.get("/ConnectionManager.xml")
def connection_manager_scpd(_: Access) -> Response:
    return _xml(dlna.CONNECTION_MANAGER_SCPD)


@router.get("/icon.png")
def icon(_: Access, settings: AppConfig) -> FileResponse:
    path = settings.static_dir / "icon-192.png"  # the app icon from the built frontend
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return FileResponse(path, media_type="image/png")


@router.api_route("/event/{service}", methods=["SUBSCRIBE", "UNSUBSCRIBE"])
def events(service: str, request: Request, _: Access) -> Response:
    """Accepted, so picky clients carry on – the library changes are not sent as events."""
    if request.method == "UNSUBSCRIBE":
        return Response()
    return Response(headers={"SID": f"uuid:{uuid.uuid4()}", "TIMEOUT": "Second-1800"})


# --- Browse ------------------------------------------------------------------------------

ROOT = "0"
CHANNELS = "channels"
RECENT = "recent"
PLAYLISTS = "playlists"


class NoSuchObjectError(Exception):
    pass


def _ready(user: User | None) -> Select[Video]:
    query = select(Video).where(Video.status == VideoStatus.READY, Video.file_path.is_not(None))
    return visible_videos(query, user) if user is not None else query


def _count(db: Session, query: Select[*tuple[Any, ...]]) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def _channels(user: User | None) -> Select[Channel, int]:
    count = func.count(Video.id).label("videos")
    query = (
        select(Channel, count)
        .join(Video, Video.channel_id == Channel.id)
        .where(Video.status == VideoStatus.READY, Video.file_path.is_not(None))
        .group_by(Channel.id)
        .order_by(func.lower(Channel.name), Channel.id)
    )
    condition = channel_filter(user, Channel.id) if user is not None else None
    return query if condition is None else query.where(condition)


def _playlists(user: User | None) -> Select[Playlist]:
    if user is None:
        return select(Playlist).where(false())
    # Only lists with something to play – an empty folder on the TV just confuses.
    filled = (
        _ready(user)
        .join(PlaylistItem, PlaylistItem.video_id == Video.id)
        .with_only_columns(PlaylistItem.playlist_id)
    )
    return (
        select(Playlist)
        .where(Playlist.user_id == user.id, Playlist.id.in_(filled))
        .order_by(Playlist.is_watch_later.desc(), func.lower(Playlist.name))
    )


def _playlist_videos(user: User | None, playlist_id: int) -> Select[Video]:
    return (
        _ready(user)
        .join(PlaylistItem, PlaylistItem.video_id == Video.id)
        .where(PlaylistItem.playlist_id == playlist_id)
        .order_by(PlaylistItem.position, PlaylistItem.id)
    )


@dataclass
class Browser:
    db: Session
    user: User | None
    base_url: str

    def _item(self, video: Video, parent: str) -> dlna.Item:
        suffix = Path(video.file_path or "").suffix.lower()
        return dlna.Item(
            id=f"{parent}/v{video.id}",
            parent=parent,
            title=video.title,
            url=f"{self.base_url}/dlna/media/{video.id}{suffix}",
            mime=VIDEO_MIME.get(suffix, "video/mp4"),
            size=video.filesize,
            duration_s=video.duration_s,
            width=video.width,
            height=video.height,
            published=video.upload_date,
            creator=video.channel.name if video.channel else None,
            thumbnail=(
                f"{self.base_url}/dlna/thumbs/{video.id}.jpg" if video.thumbnail_path else None
            ),
        )

    def _videos(self, object_id: str) -> Select[Video]:
        if object_id == RECENT:
            return _ready(self.user).order_by(Video.downloaded_at.desc(), Video.id.desc())
        kind, _, number = object_id.partition("-")
        if not number.isdigit():
            raise NoSuchObjectError(object_id)
        if kind == "channel":
            if not self._channel(int(number)):
                raise NoSuchObjectError(object_id)
            return (
                _ready(self.user)
                .where(Video.channel_id == int(number))
                .order_by(Video.upload_date.desc(), Video.id.desc())
            )
        if kind == "playlist":
            if self._playlist(int(number)) is None:
                raise NoSuchObjectError(object_id)
            return _playlist_videos(self.user, int(number))
        raise NoSuchObjectError(object_id)

    def _channel(self, channel_id: int) -> tuple[Channel, int] | None:
        row = self.db.execute(_channels(self.user).where(Channel.id == channel_id)).first()
        return (row[0], row[1]) if row else None

    def _playlist(self, playlist_id: int) -> Playlist | None:
        return self.db.scalar(_playlists(self.user).where(Playlist.id == playlist_id))

    def _playlist_title(self, playlist: Playlist) -> str:
        return "Später ansehen" if playlist.is_watch_later else playlist.name

    def _top(self) -> list[dlna.Container | dlna.Item]:
        entries: list[dlna.Container | dlna.Item] = [
            dlna.Container(CHANNELS, ROOT, "Kanäle", _count(self.db, _channels(self.user))),
            dlna.Container(
                RECENT,
                ROOT,
                "Zuletzt hinzugefügt",
                min(RECENT_COUNT, _count(self.db, _ready(self.user))),
            ),
        ]
        if self.user is not None:
            entries.append(
                dlna.Container(PLAYLISTS, ROOT, "Playlists", _count(self.db, _playlists(self.user)))
            )
        return entries

    def metadata(self, object_id: str) -> dlna.Container | dlna.Item:
        if object_id == ROOT:
            return dlna.Container(ROOT, "-1", "TubeVault", len(self._top()))
        for entry in self._top():
            if entry.id == object_id:
                return entry
        parent, _, video = object_id.rpartition("/v")
        if parent and video.isdigit():
            found = self.db.scalar(self._videos(parent).where(Video.id == int(video)))
            if found is None:
                raise NoSuchObjectError(object_id)
            return self._item(found, parent)
        kind, _, number = object_id.partition("-")
        if kind == "channel" and number.isdigit() and (row := self._channel(int(number))):
            return dlna.Container(object_id, CHANNELS, row[0].name, row[1])
        if kind == "playlist" and number.isdigit():
            playlist = self._playlist(int(number))
            if playlist is not None:
                count = _count(self.db, _playlist_videos(self.user, playlist.id))
                return dlna.Container(object_id, PLAYLISTS, self._playlist_title(playlist), count)
        raise NoSuchObjectError(object_id)

    def children(
        self, object_id: str, start: int, count: int
    ) -> tuple[list[dlna.Container | dlna.Item], int]:
        """One page of a folder and how many entries it has in total."""
        limit = min(count or MAX_PAGE, MAX_PAGE)
        if object_id == ROOT:
            top = self._top()
            return top[start : start + limit], len(top)
        if object_id == CHANNELS:
            channels = _channels(self.user)
            rows = self.db.execute(channels.offset(start).limit(limit)).all()
            entries: list[dlna.Container | dlna.Item] = [
                dlna.Container(f"channel-{channel.id}", CHANNELS, channel.name, videos)
                for channel, videos in rows
            ]
            return entries, _count(self.db, channels)
        if object_id == PLAYLISTS:
            lists = _playlists(self.user)
            playlists = list(self.db.scalars(lists.offset(start).limit(limit)))
            entries = [
                dlna.Container(
                    f"playlist-{playlist.id}",
                    PLAYLISTS,
                    self._playlist_title(playlist),
                    _count(self.db, _playlist_videos(self.user, playlist.id)),
                )
                for playlist in playlists
            ]
            return entries, _count(self.db, lists)
        query = self._videos(object_id)
        total = _count(self.db, query)
        if object_id == RECENT:
            total = min(total, RECENT_COUNT)
            limit = max(0, min(limit, total - start))
        videos = self.db.scalars(
            query.options(selectinload(Video.channel)).offset(start).limit(limit)
        )
        return [self._item(video, object_id) for video in videos], total


def _number(value: str | None) -> int:
    try:
        return max(0, int(value or 0))
    except ValueError:
        return 0


def _update_id(db: Session) -> str:
    """Changes whenever videos come or go, so clients know to reload their lists."""
    count, highest = db.execute(
        select(func.count(Video.id), func.max(Video.id)).where(Video.status == VideoStatus.READY)
    ).one()
    return str(((highest or 0) * 7919 + count) % 2**32)


def _browse(browser: Browser, args: dict[str, str]) -> bytes:
    object_id = args.get("ObjectID", ROOT)
    flag = args.get("BrowseFlag", "BrowseDirectChildren")
    try:
        if flag == "BrowseMetadata":
            entries: list[dlna.Container | dlna.Item] = [browser.metadata(object_id)]
            total = 1
        elif flag == "BrowseDirectChildren":
            entries, total = browser.children(
                object_id, _number(args.get("StartingIndex")), _number(args.get("RequestedCount"))
            )
        else:
            return dlna.soap_fault(402, "Invalid Args")
    except NoSuchObjectError:
        return dlna.soap_fault(701, "No such object")
    return dlna.soap_response(
        dlna.CONTENT_DIRECTORY,
        "Browse",
        {
            "Result": dlna.didl(entries),
            "NumberReturned": str(len(entries)),
            "TotalMatches": str(total),
            "UpdateID": _update_id(browser.db),
        },
    )


SOURCE_PROTOCOLS = ",".join(f"http-get:*:{mime}:*" for mime in sorted(set(VIDEO_MIME.values())))


@router.post("/control/{service}")
async def control(service: str, request: Request, access: Access, db: DbSession) -> Response:
    try:
        action, args = dlna.parse_soap(await request.body())
    except (ParseError, ValueError):
        return _xml(dlna.soap_fault(401, "Invalid Action"), 500)
    base_url = f"http://{request.headers.get('host') or request.url.netloc}"
    if service == "ContentDirectory":
        kind = dlna.CONTENT_DIRECTORY
        if action == "Browse":
            body = _browse(Browser(db, access.user, base_url), args)
            return _xml(body, 500 if b"<s:Fault>" in body else 200)
        if action == "GetSearchCapabilities":
            return _xml(dlna.soap_response(kind, action, {"SearchCaps": ""}))
        if action == "GetSortCapabilities":
            return _xml(dlna.soap_response(kind, action, {"SortCaps": ""}))
        if action == "GetSystemUpdateID":
            return _xml(dlna.soap_response(kind, action, {"Id": _update_id(db)}))
    elif service == "ConnectionManager":
        kind = dlna.CONNECTION_MANAGER
        if action == "GetProtocolInfo":
            values = {"Source": SOURCE_PROTOCOLS, "Sink": ""}
            return _xml(dlna.soap_response(kind, action, values))
        if action == "GetCurrentConnectionIDs":
            return _xml(dlna.soap_response(kind, action, {"ConnectionIDs": "0"}))
    return _xml(dlna.soap_fault(401, "Invalid Action"), 500)


# --- files -------------------------------------------------------------------------------


def _visible_video(db: Session, access: DlnaAccess, video_id: int) -> Video:
    video = db.scalar(_ready(access.user).where(Video.id == video_id))
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video nicht gefunden")
    return video


DLNA_HEADERS = {
    "transferMode.dlna.org": "Streaming",
    "contentFeatures.dlna.org": dlna.DLNA_FEATURES,
    "Cache-Control": "no-store",
}


@router.api_route("/media/{video_id}.{ext}", methods=["GET", "HEAD"])
def media(
    video_id: int, ext: str, access: Access, db: DbSession, settings: AppConfig
) -> FileResponse:
    video = _visible_video(db, access, video_id)
    path = _media_file(settings.media_dir, video.file_path)
    mime = VIDEO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=mime, headers=DLNA_HEADERS)


@router.get("/thumbs/{video_id}.jpg")
def thumb(video_id: int, access: Access, db: DbSession, settings: AppConfig) -> FileResponse:
    video = _visible_video(db, access, video_id)
    path = _media_file(settings.media_dir, video.thumbnail_path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    headers = {"Cache-Control": "public, max-age=86400", "transferMode.dlna.org": "Interactive"}
    return FileResponse(path, media_type=mime, headers=headers)
