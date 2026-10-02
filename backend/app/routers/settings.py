"""App settings (download quality, subtitles, concurrency)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import AdminUser, Context, CurrentUser, DbSession
from app.services.app_settings import AppSettings, load_app_settings, save_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(_: CurrentUser, db: DbSession) -> AppSettings:
    return load_app_settings(db)


@router.put("")
def update_settings(body: AppSettings, _: AdminUser, db: DbSession, ctx: Context) -> AppSettings:
    saved = save_app_settings(db, body)
    ctx.downloads.wake()  # concurrency may have changed
    return saved
