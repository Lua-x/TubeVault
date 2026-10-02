"""App settings that can be changed in the UI. Stored as one JSON document."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models import Setting

SETTINGS_KEY = "app"

Container = Literal["mp4", "mkv"]
MaxHeight = Literal[2160, 1440, 1080, 720, 480, 360]
SponsorBlockMode = Literal["off", "skip", "cut"]
SponsorBlockCategory = Literal[
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "music_offtopic", "filler"
]


def _default_categories() -> list[SponsorBlockCategory]:
    return ["sponsor", "selfpromo", "interaction"]


class DownloadOptions(BaseModel):
    """Options that decide how a single video is downloaded."""

    container: Container = "mp4"
    max_height: MaxHeight | None = 1080
    prefer_h264: bool = True
    subtitles: bool = True
    auto_subtitles: bool = True
    subtitle_languages: list[str] = Field(default_factory=lambda: ["de", "en"])
    # "skip": the player jumps over segments; "cut": they are removed from the file.
    sponsorblock_mode: SponsorBlockMode = "off"
    sponsorblock_categories: list[SponsorBlockCategory] = Field(
        default_factory=lambda: _default_categories()
    )

    @field_validator("subtitle_languages")
    @classmethod
    def _clean_languages(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for lang in value:
            code = lang.strip().lower()
            if code and code not in cleaned and len(code) <= 16:
                cleaned.append(code)
        return cleaned


HwAccel = Literal["none", "vaapi", "nvenc"]
TranscodeHeight = Literal[2160, 1440, 1080, 720, 480]
_DRI_DEVICE = re.compile(r"^/dev/dri/[A-Za-z0-9_]+$")


class TranscodeOptions(BaseModel):
    """How videos are converted for devices that can't play the file directly."""

    hwaccel: HwAccel = "none"
    vaapi_device: str = "/dev/dri/renderD128"
    # Upper limit for converted video; the original file is never touched.
    max_height: TranscodeHeight = 1080
    max_sessions: int = Field(default=2, ge=1, le=8)
    cache_gb: int = Field(default=10, ge=1, le=2000)

    @field_validator("vaapi_device")
    @classmethod
    def _check_device(cls, value: str) -> str:
        value = value.strip()
        if not _DRI_DEVICE.match(value):
            raise ValueError("Gerät muss unter /dev/dri liegen, z. B. /dev/dri/renderD128")
        return value


class AppSettings(BaseModel):
    downloads: DownloadOptions = Field(default_factory=DownloadOptions)
    max_concurrent_downloads: int = Field(default=2, ge=1, le=5)
    transcoding: TranscodeOptions = Field(default_factory=TranscodeOptions)


QUEUE_PAUSED_KEY = "queue_paused"


def queue_paused(db: Session) -> bool:
    row = db.get(Setting, QUEUE_PAUSED_KEY)
    return bool(row and row.value)


def set_queue_paused(db: Session, paused: bool) -> None:
    row = db.get(Setting, QUEUE_PAUSED_KEY)
    if row is None:
        db.add(Setting(key=QUEUE_PAUSED_KEY, value=paused))
    else:
        row.value = paused
    db.commit()


def load_app_settings(db: Session) -> AppSettings:
    row = db.get(Setting, SETTINGS_KEY)
    if row is None or not isinstance(row.value, dict):
        return AppSettings()
    return AppSettings.model_validate(row.value)


def save_app_settings(db: Session, settings: AppSettings) -> AppSettings:
    row = db.get(Setting, SETTINGS_KEY)
    value = settings.model_dump(mode="json")
    if row is None:
        db.add(Setting(key=SETTINGS_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return settings
