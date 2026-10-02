"""Application configuration from environment variables."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Infrastructure settings. App behaviour lives in the database (see AppSettings)."""

    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=False, validate_assignment=True
    )

    host: str = "0.0.0.0"
    port: int = 8096
    base_path: str = ""
    forwarded_allow_ips: str = "*"
    log_level: LogLevel = "INFO"

    config_dir: Path = Path("/config")
    media_dir: Path = Path("/media")
    database_url: str | None = None
    static_dir: Path = Path(__file__).parent / "static"

    admin_user: str | None = None
    admin_password: str | None = None
    session_days: int = 30

    ytdlp_auto_update: bool = True

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        return f"/{value}" if value else ""

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @cached_property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.config_dir / 'tubevault.db'}"

    @property
    def logs_dir(self) -> Path:
        return self.config_dir / "logs"

    @property
    def runtime_dir(self) -> Path:
        """Writable directory for components updated at runtime (yt-dlp)."""
        return self.config_dir / ".runtime"

    @property
    def cache_dir(self) -> Path:
        """Converted streams (HLS segments, remuxed files); safe to delete at any time."""
        return self.media_dir / ".tubevault" / "cache"

    @property
    def temp_dir(self) -> Path:
        """Partial downloads, on the media volume so finished files can be moved atomically."""
        return self.media_dir / ".tubevault" / "tmp"
