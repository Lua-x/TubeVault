"""Playback on every device: remuxed MP4s, HLS transcoding and the hardware for it."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.core.deps import AdminUser, AppConfig, Context, CurrentUser, DbSession
from app.models import Video
from app.routers.media import _media_file, _video
from app.schemas.playback import (
    HardwareOut,
    HwTestOut,
    HwTestRequest,
    PlaybackInfo,
    RemuxStatus,
    TranscodeSessionOut,
)
from app.services.app_settings import load_app_settings
from app.services.transcode import (
    QUALITIES,
    ProbeError,
    available_heights,
    can_copy_into_mp4,
    codec_string,
    hls_playlist,
    probe,
    target_height,
)
from app.workers.transcoder import (
    RemuxJob,
    Source,
    TooManySessionsError,
    TranscodeError,
    detect_hardware,
    run_hwaccel_test,
)

router = APIRouter(tags=["playback"])

HLS_CACHE = "private, max-age=3600"


def _source(db: DbSession, settings: AppConfig, video_id: int) -> tuple[Video, Source]:
    video = _video(db, video_id)
    path = _media_file(settings.media_dir, video.file_path)
    try:
        info = probe(path)
    except ProbeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Video kann nicht gelesen werden: {exc}"
        ) from exc
    return video, Source(video_id=video.id, path=path, info=info)


def _quality(quality: str) -> str:
    if quality not in QUALITIES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unbekannte Qualität")
    return quality


def _codec(stored: str | None, probed: str | None) -> str | None:
    """The full RFC 6381 string; yt-dlp sometimes stores just "vp9" or "opus"."""
    if stored and "." in stored:
        return stored
    return codec_string(probed) or (stored if stored and stored.lower() != "none" else None)


@router.get("/videos/{video_id}/playback")
def playback_info(
    video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig
) -> PlaybackInfo:
    video, source = _source(db, settings, video_id)
    info = source.info
    options = load_app_settings(db).transcoding
    return PlaybackInfo(
        container=video.container,
        video_codec=_codec(video.vcodec, info.video_codec),
        audio_codec=_codec(video.acodec, info.audio_codec),
        width=info.width,
        height=info.height,
        duration=info.duration,
        can_remux=can_copy_into_mp4(info),
        qualities=available_heights(info.height, options.max_height),
        transcode_height=target_height("source", info.height, options.max_height),
    )


@router.get("/videos/{video_id}/hls/{quality}/index.m3u8")
def hls_index(
    video_id: int, quality: str, _: CurrentUser, db: DbSession, settings: AppConfig
) -> Response:
    _quality(quality)
    source = _source(db, settings, video_id)[1]
    return Response(
        hls_playlist(source.info.duration),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/videos/{video_id}/hls/{quality}/{index}.ts")
def hls_segment(
    video_id: int,
    quality: str,
    index: int,
    _: CurrentUser,
    db: DbSession,
    settings: AppConfig,
    ctx: Context,
) -> FileResponse:
    _quality(quality)
    source = _source(db, settings, video_id)[1]
    # Don't keep a database transaction open while ffmpeg works.
    db.rollback()
    try:
        path = ctx.transcoder.segment(source, quality, index)
    except IndexError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segment gibt es nicht") from exc
    except TooManySessionsError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except TranscodeError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
    return FileResponse(path, media_type="video/mp2t", headers={"Cache-Control": HLS_CACHE})


def _remux_status(job: RemuxJob | None) -> RemuxStatus:
    if job is None:
        return RemuxStatus(state="none")
    return RemuxStatus(state=job.state, progress=round(job.progress, 3), error=job.error)


@router.post("/videos/{video_id}/remux")
def start_remux(
    video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig, ctx: Context
) -> RemuxStatus:
    source = _source(db, settings, video_id)[1]
    try:
        return _remux_status(ctx.transcoder.remux(source))
    except TranscodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/videos/{video_id}/remux")
def remux_status(
    video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig, ctx: Context
) -> RemuxStatus:
    source = _source(db, settings, video_id)[1]
    return _remux_status(ctx.transcoder.remux_status(source))


@router.get("/videos/{video_id}/remux.mp4")
def remux_file(
    video_id: int, _: CurrentUser, db: DbSession, settings: AppConfig, ctx: Context
) -> FileResponse:
    source = _source(db, settings, video_id)[1]
    path = ctx.transcoder.remux_file(source)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Noch nicht vorbereitet")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": HLS_CACHE})


# --- administration ------------------------------------------------------------------


@router.get("/transcoding/hardware")
def hardware(_: AdminUser) -> HardwareOut:
    info = detect_hardware()
    return HardwareOut(
        render_devices=info.render_devices, nvidia=info.nvidia, encoders=info.encoders
    )


@router.post("/transcoding/test")
def hwaccel_test(body: HwTestRequest, _: AdminUser) -> HwTestOut:
    if body.hwaccel == "vaapi" and not body.vaapi_device.startswith("/dev/dri/"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ungültiges Gerät")
    result = run_hwaccel_test(body.hwaccel, body.vaapi_device)
    return HwTestOut(ok=result.ok, seconds=round(result.seconds, 2), message=result.message)


@router.get("/transcoding/sessions")
def transcode_sessions(_: AdminUser, db: DbSession, ctx: Context) -> list[TranscodeSessionOut]:
    sessions = ctx.transcoder.sessions()
    rows = db.execute(
        select(Video.id, Video.title).where(Video.id.in_([s.video_id for s in sessions]))
    )
    titles = {row.id: row.title for row in rows}
    return [
        TranscodeSessionOut(
            video_id=s.video_id,
            title=titles.get(s.video_id),
            quality=s.quality,
            height=s.height,
            mode=s.mode,
            position_s=s.position_s,
            paused=s.paused,
            idle_s=round(s.idle_s, 1),
        )
        for s in sessions
    ]
