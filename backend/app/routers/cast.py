"""Playing on a TV: a signed link the TV can fetch without a login."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.core.deps import AppConfig, Context, CurrentUser, DbSession
from app.core.urls import public_base
from app.models import User, Video, VideoStatus
from app.routers.media import MEDIA_CACHE, _media_file, _video
from app.routers.playback import _source, prepared_response
from app.services import casting
from app.services.access import ensure_visible
from app.services.transcode import can_copy_into_mp4
from app.workers.transcoder import TranscodeError

router = APIRouter(tags=["cast"])

MP4_SUFFIXES = (".mp4", ".m4v", ".mov")


class CastLink(BaseModel):
    url: str
    # The same link below /api – for the browser itself, on whatever address it uses.
    path: str
    expires_at: datetime


@router.post("/videos/{video_id}/cast")
def cast_link(
    video_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> CastLink:
    """A link to this video for a TV – valid for a few hours, for this account only."""
    video = ensure_visible(user, db.get(Video, video_id))
    if video.status is not VideoStatus.READY or not video.file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "Das Video ist noch nicht fertig geladen.")
    if Path(video.file_path).suffix.lower() not in MP4_SUFFIXES:
        # Matroska & Co.: TVs want MP4. Start repacking now, so it's ready when they ask.
        source = _source(db, settings, video.id, user)[1]
        if not can_copy_into_mp4(source.info):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Dieses Format kann TubeVault nicht für den Fernseher umverpacken.",
            )
        try:
            ctx.transcoder.remux(source)
        except TranscodeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    expires, signature = casting.sign(db, user.id, video.id)
    path = f"cast/{user.id}/{video.id}/{expires}/{signature}.mp4"
    return CastLink(
        url=f"{public_base(request, settings)}/api/{path}",
        path=path,
        expires_at=datetime.fromtimestamp(expires, UTC),
    )


@router.api_route("/cast/{user_id}/{video_id}/{expires}/{signature}.mp4", methods=["GET", "HEAD"])
def cast_stream(
    user_id: int,
    video_id: int,
    expires: int,
    signature: str,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> Response:
    if not casting.verify(db, user_id, video_id, expires, signature):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link abgelaufen oder ungültig")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link abgelaufen oder ungültig")
    # Rights are checked again: a link outlives a change of what the account may see.
    video = _video(db, video_id, user)
    path = _media_file(settings.media_dir, video.file_path)
    if path.suffix.lower() in MP4_SUFFIXES:
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": MEDIA_CACHE})
    return prepared_response(ctx.transcoder, _source(db, settings, video_id, user)[1], None)
