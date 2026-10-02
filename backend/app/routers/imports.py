"""Importing existing video files (admins only)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import AdminUser, Context
from app.services.app_settings import load_app_settings
from app.services.importer import ImportSkippedError
from app.workers.library_tasks import Progress, TaskBusyError

router = APIRouter(prefix="/import", tags=["import"])
log = logging.getLogger(__name__)


class CandidateOut(BaseModel):
    key: str
    root: Literal["import", "media"]
    relative: str
    size: int
    youtube_id: str | None
    source: str | None
    title: str
    status: Literal["ready", "known", "unknown"]


class ImportOverview(BaseModel):
    import_dir: str
    import_dir_exists: bool
    scanned_at: str | None
    candidates: list[CandidateOut]


class ImportRequest(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=10000)
    mode: Literal["move", "copy", "keep"] = "move"
    fetch_metadata: bool = True


def _busy(exc: TaskBusyError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("")
def overview(_: AdminUser, ctx: Context) -> ImportOverview:
    importer = ctx.importer
    result = importer.last_scan
    return ImportOverview(
        import_dir=str(importer.import_dir),
        import_dir_exists=importer.import_dir.is_dir(),
        scanned_at=result.scanned_at if result else None,
        candidates=[CandidateOut.model_validate(c, from_attributes=True) for c in result.candidates]
        if result
        else [],
    )


@router.post("/scan")
def start_scan(_: AdminUser, ctx: Context) -> dict[str, Any]:
    def work(progress: Progress) -> str:
        with ctx.sessions() as db:
            result = ctx.importer.run_scan(db)
        ready = sum(1 for c in result.candidates if c.status == "ready")
        return f"{len(result.candidates)} Dateien gefunden, {ready} lassen sich importieren"

    try:
        return ctx.library_tasks.run("import-scan", "Ordner durchsuchen", work).as_dict()
    except TaskBusyError as exc:
        raise _busy(exc) from exc


@router.post("/run")
def start_import(body: ImportRequest, user: AdminUser, ctx: Context) -> dict[str, Any]:
    candidates = [c for c in ctx.importer.find(body.keys) if c.status == "ready"]
    if not candidates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Keine importierbaren Dateien ausgewählt. Bitte erst neu durchsuchen.",
        )
    if body.mode == "keep" and any(c.root != "media" for c in candidates):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nur Dateien unter /media können an ihrem Platz bleiben.",
        )
    user_id = user.id

    def work(progress: Progress) -> str:
        imported, skipped, failed = 0, 0, 0
        progress.total(len(candidates))
        with ctx.sessions() as db:
            library = load_app_settings(db).library
            for candidate in candidates:
                try:
                    video = ctx.importer.import_one(
                        db,
                        candidate,
                        mode=body.mode,
                        fetch_metadata=body.fetch_metadata,
                        layout=library.layout,
                        write_nfo=library.write_nfo,
                        user_id=user_id,
                    )
                    imported += 1
                    ctx.events.publish("video.updated", video={"id": video.id})
                except ImportSkippedError:
                    db.rollback()
                    skipped += 1
                except Exception:
                    db.rollback()
                    failed += 1
                    log.exception("Import von %s fehlgeschlagen", candidate.relative)
                progress.step(candidate.title)
            ctx.importer.run_scan(db)
        parts = [f"{imported} importiert"]
        if skipped:
            parts.append(f"{skipped} übersprungen")
        if failed:
            parts.append(f"{failed} fehlgeschlagen (siehe Log)")
        return ", ".join(parts)

    label = f"{len(candidates)} Videos importieren"
    try:
        return ctx.library_tasks.run("import", label, work).as_dict()
    except TaskBusyError as exc:
        raise _busy(exc) from exc
