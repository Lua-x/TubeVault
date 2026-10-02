"""Channel artwork (avatar and banner)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.core.deps import AppConfig, CurrentUser, DbSession
from app.models import Channel
from app.services.subscriptions import channel_media_path

router = APIRouter(prefix="/channels", tags=["channels"])


def _image(db: DbSession, settings: AppConfig, channel_id: int, kind: str) -> FileResponse:
    path = channel_media_path(settings.media_dir, db.get(Channel, channel_id), kind)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bild nicht vorhanden")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/{channel_id}/avatar")
def avatar(channel_id: int, _: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    return _image(db, settings, channel_id, "avatar")


@router.get("/{channel_id}/banner")
def banner(channel_id: int, _: CurrentUser, db: DbSession, settings: AppConfig) -> FileResponse:
    return _image(db, settings, channel_id, "banner")
