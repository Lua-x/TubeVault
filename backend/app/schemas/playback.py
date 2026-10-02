from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.services.app_settings import HwAccel


class PlaybackInfo(BaseModel):
    """What the player needs to decide between direct play, remux and transcoding."""

    container: str | None
    # RFC 6381 codec strings for canPlayType(), e.g. "avc1.640028" and "mp4a.40.2".
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    duration: float
    can_remux: bool
    # Heights the quality menu offers below the original.
    qualities: list[int]
    # Height used when the original has to be converted.
    transcode_height: int


class RemuxStatus(BaseModel):
    state: Literal["none", "running", "ready", "failed"]
    progress: float = 0.0
    error: str | None = None


class TranscodeSessionOut(BaseModel):
    video_id: int
    title: str | None
    quality: str
    height: int
    mode: str
    position_s: float
    paused: bool
    idle_s: float


class HardwareOut(BaseModel):
    render_devices: list[str]
    nvidia: bool
    encoders: dict[str, bool]


class HwTestRequest(BaseModel):
    hwaccel: HwAccel
    vaapi_device: str = "/dev/dri/renderD128"


class HwTestOut(BaseModel):
    ok: bool
    seconds: float
    message: str
