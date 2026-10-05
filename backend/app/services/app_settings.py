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
MaxComments = Literal[100, 500, 1000, 5000]
SponsorBlockCategory = Literal[
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "music_offtopic", "filler"
]


def _default_categories() -> list[SponsorBlockCategory]:
    return ["sponsor", "selfpromo", "interaction"]


class DownloadOptions(BaseModel):
    """Options that decide how a single video is downloaded."""

    container: Container = "mp4"
    # None: the best available quality (up to 8K, if YouTube has it).
    max_height: MaxHeight | None = None
    prefer_h264: bool = True
    subtitles: bool = True
    auto_subtitles: bool = True
    subtitle_languages: list[str] = Field(default_factory=lambda: ["de", "en"])
    # "skip": the player jumps over segments; "cut": they are removed from the file.
    sponsorblock_mode: SponsorBlockMode = "off"
    sponsorblock_categories: list[SponsorBlockCategory] = Field(
        default_factory=lambda: _default_categories()
    )
    # Save the top comments (with replies) to read them offline. Off unless wanted.
    comments: bool = False
    max_comments: MaxComments = 500

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


Layout = Literal["tubevault", "series"]


class LibraryOptions(BaseModel):
    """How files are laid out on disk, e.g. for Jellyfin, Emby, Kodi or Plex."""

    # "tubevault": <Channel>/<Year>/<Title> [id]
    # "series":    <Channel>/Season <Year>/<YYYY-MM-DD> - <Title> [id]  (channel = show)
    layout: Layout = "tubevault"
    write_nfo: bool = True


class AutomationOptions(BaseModel):
    # Look at the channels' RSS feeds every 15 minutes to find new uploads sooner.
    rss: bool = True
    # Right after an upload YouTube often only has low resolutions; fetch the better
    # version within the first days.
    upgrade_quality: bool = True


class BackupOptions(BaseModel):
    """Daily automatic backups of the database to /config/backups."""

    auto: bool = True
    keep: int = Field(default=7, ge=1, le=60)


class AnalysisOptions(BaseModel):
    """Background work per video, done once, at low priority."""

    # Small preview pictures while seeking.
    trickplay: bool = True
    # Measure how loud a video is, so the player can even out loud and quiet ones.
    loudness: bool = True


SpeechModel = Literal["tiny", "base", "small"]
_LANGUAGE = re.compile(r"^[a-z]{2,3}$")


class SpeechOptions(BaseModel):
    """Subtitles from speech recognition – only once an admin has set it up."""

    # Bigger is more accurate and slower: tiny ~75 MB, base ~145 MB, small ~485 MB.
    model: SpeechModel = "base"
    # "auto": recognised from the first seconds; otherwise e.g. "de".
    language: str = "auto"
    # New own videos (import) without subtitles get some by themselves.
    auto_own_videos: bool = False

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        value = value.strip().lower()
        if value != "auto" and not _LANGUAGE.match(value):
            raise ValueError("Sprache als Kürzel wie de oder en – oder auto")
        return value


class DlnaOptions(BaseModel):
    """Smart TVs, consoles and VLC find the library in the home network (no login)."""

    enabled: bool = False
    name: str = Field(default="TubeVault", min_length=1, max_length=64)
    # Whose view the TV gets (e.g. a kids profile); None = every video.
    user_id: int | None = None


class AppSettings(BaseModel):
    # Off: a pure media server – nothing is fetched from YouTube or SponsorBlock any more,
    # no subscriptions are checked, no downloads run. The library stays as it is.
    youtube_enabled: bool = True
    downloads: DownloadOptions = Field(default_factory=DownloadOptions)
    max_concurrent_downloads: int = Field(default=2, ge=1, le=5)
    transcoding: TranscodeOptions = Field(default_factory=TranscodeOptions)
    library: LibraryOptions = Field(default_factory=LibraryOptions)
    backup: BackupOptions = Field(default_factory=BackupOptions)
    automation: AutomationOptions = Field(default_factory=AutomationOptions)
    dlna: DlnaOptions = Field(default_factory=DlnaOptions)
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)
    speech: SpeechOptions = Field(default_factory=SpeechOptions)


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


def youtube_enabled(db: Session) -> bool:
    return load_app_settings(db).youtube_enabled


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
