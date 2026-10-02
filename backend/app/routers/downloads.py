"""The download queue: list, cancel, retry and clear jobs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.deps import Context, CurrentUser, DbSession
from app.models import ACTIVE_JOB_STATUSES, DownloadJob, JobStatus, Video
from app.schemas.common import Page
from app.schemas.jobs import JobOut
from app.workers.download_manager import job_payload, load_job

router = APIRouter(prefix="/downloads", tags=["downloads"])

FINISHED = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


def _get_job(db: DbSession, job_id: int) -> DownloadJob:
    job = load_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Download nicht gefunden")
    return job


@router.get("")
def list_jobs(
    _: CurrentUser,
    db: DbSession,
    state: Literal["active", "finished", "all"] = "all",
    limit: int = Query(default=100, ge=1, le=500),
) -> Page[JobOut]:
    query = select(DownloadJob)
    if state == "active":
        query = query.where(DownloadJob.status.in_(ACTIVE_JOB_STATUSES))
    elif state == "finished":
        query = query.where(DownloadJob.status.in_(FINISHED))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    jobs = db.scalars(
        query.options(selectinload(DownloadJob.video).selectinload(Video.channel))
        .order_by(DownloadJob.created_at.desc(), DownloadJob.id.desc())
        .limit(limit)
    )
    return Page(items=[JobOut.model_validate(j) for j in jobs], total=total)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Download läuft nicht mehr.")
    if not ctx.downloads.cancel(job.id):
        job.status = JobStatus.CANCELLED
        job.next_attempt_at = None
        db.commit()
        ctx.events.publish("job.updated", job=job_payload(_get_job(db, job_id)))
    # A running job reports its own state change once it has stopped.
    db.refresh(job)
    return JobOut.model_validate(job)


@router.post("/{job_id}/retry")
def retry_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED) and not (
        job.status is JobStatus.QUEUED and job.next_attempt_at is not None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dieser Download kann nicht wiederholt werden."
        )
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.next_attempt_at = None
    job.error_kind = None
    job.error_message = None
    job.finished_at = None
    job.progress = 0.0
    db.commit()
    payload = job_payload(_get_job(db, job_id))
    ctx.events.publish("job.updated", job=payload)
    ctx.downloads.wake()
    return JobOut.model_validate(payload)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> None:
    job = _get_job(db, job_id)
    if job.status not in FINISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Laufende Downloads bitte erst abbrechen.")
    db.delete(job)
    db.commit()
    ctx.events.publish("job.deleted", job_id=job_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_finished(_: CurrentUser, db: DbSession, ctx: Context) -> None:
    db.execute(delete(DownloadJob).where(DownloadJob.status.in_(FINISHED)))
    db.commit()
    ctx.events.publish("jobs.cleared")
