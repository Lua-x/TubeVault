from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class DeviceOptions(BaseModel):
    """What can be saved onto a device: the original, or a compact H.264 version."""

    duration: float
    source_height: int | None
    original_size: int
    # height → estimated bytes, for sizes up to the original's height
    estimates: dict[int, int]
    can_remux: bool  # the original's codecs fit into an MP4 as they are
    audio_size: int | None = None  # only the sound, as M4A; None without a sound track


class DeviceEstimateRequest(BaseModel):
    video_ids: list[int] = Field(max_length=5000)


class DeviceEstimate(BaseModel):
    """Totals for saving several videos at once."""

    count: int
    original_size: int
    audio_size: int = 0
    estimates: dict[int, int]  # height → estimated bytes


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
