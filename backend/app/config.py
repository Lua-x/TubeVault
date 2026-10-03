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
    # Optional folder with existing videos to import (mounted read-only is fine for copying).
    import_dir: Path = Path("/import")
    database_url: str | None = None
    static_dir: Path = Path(__file__).parent / "static"

    admin_user: str | None = None
    admin_password: str | None = None
    session_days: int = 30

    ytdlp_auto_update: bool = True

    # Optional login via an OpenID Connect provider (Authelia, Authentik, Keycloak, …).
    # Configured here rather than in the UI, so the client secret stays out of the
    # database and backups.
    public_url: str | None = None  # e.g. https://tube.example.com – for the redirect URI
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_name: str = "SSO"  # shown on the button: "Mit … anmelden"
    oidc_scopes: str = "openid profile email groups"
    oidc_username_claim: str = "preferred_username"
    oidc_groups_claim: str = "groups"
    oidc_admin_group: str | None = None
    oidc_auto_create: bool = True
    oidc_token_auth: Literal["client_secret_basic", "client_secret_post"] = "client_secret_basic"
    # Off: only the provider – keep a way in (reset-password needs the console).
    password_login: bool = True

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        return f"/{value}" if value else ""

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

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
