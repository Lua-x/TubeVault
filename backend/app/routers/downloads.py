"""The download queue: list, pause, resume, cancel, retry and clear jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.deps import Context, CurrentUser, DbSession
from app.models import (
    ACTIVE_JOB_STATUSES,
    FINISHED_JOB_STATUSES,
    DownloadJob,
    ItemState,
    JobStatus,
    Video,
)
from app.schemas.common import Page
from app.schemas.jobs import JobOut
from app.services.app_settings import queue_paused, set_queue_paused
from app.services.downloader import cleanup_temp
from app.services.subscriptions import update_items_for_job
from app.workers.download_manager import job_payload, load_job

router = APIRouter(prefix="/downloads", tags=["downloads"])


class QueueState(BaseModel):
    paused: bool
    running: int
    queued: int


def _get_job(db: DbSession, job_id: int) -> DownloadJob:
    job = load_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Download nicht gefunden")
    return job


def _publish(ctx: Context, db: DbSession, job_id: int) -> JobOut:
    payload = job_payload(_get_job(db, job_id))
    ctx.events.publish("job.updated", job=payload)
    return JobOut.model_validate(payload)


def _queue_state(db: DbSession) -> QueueState:
    counts = dict(
        db.execute(
            select(DownloadJob.status, func.count())
            .where(DownloadJob.status.in_((JobStatus.RUNNING, JobStatus.QUEUED)))
            .group_by(DownloadJob.status)
        ).all()
    )
    return QueueState(
        paused=queue_paused(db),
        running=int(counts.get(JobStatus.RUNNING, 0)),
        queued=int(counts.get(JobStatus.QUEUED, 0)),
    )


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
        query = query.where(DownloadJob.status.in_(FINISHED_JOB_STATUSES))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    jobs = db.scalars(
        query.options(
            selectinload(DownloadJob.video).selectinload(Video.channel),
            selectinload(DownloadJob.subscription),
        )
        .order_by(DownloadJob.created_at.desc(), DownloadJob.id.desc())
        .limit(limit)
    )
    return Page(items=[JobOut.model_validate(j) for j in jobs], total=total)


@router.get("/state")
def get_state(_: CurrentUser, db: DbSession) -> QueueState:
    return _queue_state(db)


@router.post("/pause-all")
def pause_all(_: CurrentUser, db: DbSession, ctx: Context) -> QueueState:
    """Stop starting new downloads; running ones go back into the queue and resume later."""
    set_queue_paused(db, True)
    ctx.downloads.requeue_running()
    ctx.events.publish("queue.state", paused=True)
    return _queue_state(db)


@router.post("/resume-all")
def resume_all(_: CurrentUser, db: DbSession, ctx: Context) -> QueueState:
    set_queue_paused(db, False)
    ctx.downloads.wake()
    ctx.events.publish("queue.state", paused=False)
    return _queue_state(db)


@router.post("/retry-failed")
def retry_failed(_: CurrentUser, db: DbSession, ctx: Context) -> QueueState:
    jobs = db.scalars(select(DownloadJob).where(DownloadJob.status == JobStatus.FAILED)).all()
    for job in jobs:
        _requeue(db, job)
    db.commit()
    for job in jobs:
        _publish(ctx, db, job.id)
    ctx.downloads.wake()
    return _queue_state(db)


@router.post("/{job_id}/pause")
def pause_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Download kann nicht pausiert werden.")
    if not ctx.downloads.pause(job.id):
        job.status = JobStatus.PAUSED
        db.commit()
        return _publish(ctx, db, job_id)
    db.refresh(job)
    return JobOut.model_validate(job)


@router.post("/{job_id}/resume")
def resume_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    if job.status is not JobStatus.PAUSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Download ist nicht pausiert.")
    job.status = JobStatus.QUEUED
    job.next_attempt_at = None
    db.commit()
    ctx.downloads.wake()
    return _publish(ctx, db, job_id)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dieser Download läuft nicht mehr.")
    if not ctx.downloads.cancel(job.id):
        job.status = JobStatus.CANCELLED
        job.next_attempt_at = None
        job.finished_at = datetime.now(UTC)
        update_items_for_job(db, job.id, ItemState.REMOVED, reason="Abgebrochen")
        db.commit()
        cleanup_temp(ctx.settings.temp_dir / f"job-{job.id}")
        return _publish(ctx, db, job_id)
    # A running job reports its own state change once it has stopped.
    db.refresh(job)
    return JobOut.model_validate(job)


def _requeue(db: DbSession, job: DownloadJob) -> None:
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.next_attempt_at = None
    job.error_kind = None
    job.error_message = None
    job.finished_at = None
    job.progress = 0.0
    update_items_for_job(db, job.id, ItemState.QUEUED)


@router.post("/{job_id}/retry")
def retry_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> JobOut:
    job = _get_job(db, job_id)
    waiting = job.status is JobStatus.QUEUED and job.next_attempt_at is not None
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED) and not waiting:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dieser Download kann nicht wiederholt werden."
        )
    _requeue(db, job)
    db.commit()
    ctx.downloads.wake()
    return _publish(ctx, db, job_id)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, _: CurrentUser, db: DbSession, ctx: Context) -> None:
    job = _get_job(db, job_id)
    if job.status not in (*FINISHED_JOB_STATUSES, JobStatus.PAUSED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Laufende Downloads bitte erst abbrechen.")
    if job.status is JobStatus.PAUSED:
        update_items_for_job(db, job.id, ItemState.REMOVED, reason="Abgebrochen")
    db.delete(job)
    db.commit()
    cleanup_temp(ctx.settings.temp_dir / f"job-{job_id}")
    ctx.events.publish("job.deleted", job_id=job_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_finished(_: CurrentUser, db: DbSession, ctx: Context) -> None:
    db.execute(delete(DownloadJob).where(DownloadJob.status.in_(FINISHED_JOB_STATUSES)))
    db.commit()
    ctx.events.publish("jobs.cleared")
