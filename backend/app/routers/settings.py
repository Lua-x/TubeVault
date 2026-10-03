"""App settings (download quality, subtitles, concurrency)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.deps import AdminUser, Context, CurrentUser, DbSession
from app.services.app_settings import AppSettings, load_app_settings, save_app_settings
from app.services.dlna import SSDP_GROUP

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(_: CurrentUser, db: DbSession) -> AppSettings:
    return load_app_settings(db)


@router.put("")
def update_settings(body: AppSettings, _: AdminUser, db: DbSession, ctx: Context) -> AppSettings:
    previous = load_app_settings(db)
    before = previous.library
    library_changed = body.library != before
    if library_changed and ctx.library_tasks.busy():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Gerade läuft eine Aufgabe in der Bibliothek. Bitte warte, bis sie fertig ist.",
        )
    saved = save_app_settings(db, body)
    ctx.downloads.wake()  # concurrency may have changed
    if body.dlna.enabled != previous.dlna.enabled:
        ctx.dlna.apply()
    if body.library.layout != before.layout:
        ctx.library_tasks.relayout(body.library)
    elif body.library.write_nfo != before.write_nfo:
        ctx.library_tasks.sync_nfo(body.library)
    return saved


class DlnaStatus(BaseModel):
    running: bool
    error: str | None
    # Where TVs find the description – the address of this machine in the home network.
    description_url: str | None


@router.get("/dlna")
def dlna_status(_: AdminUser, ctx: Context) -> DlnaStatus:
    service = ctx.dlna
    return DlnaStatus(
        running=service.running,
        error=service.error,
        description_url=service.location_for(SSDP_GROUP) if service.running else None,
    )
