"""Absolute addresses of this server – for links that leave the browser."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings


def public_base(request: Request, settings: Settings) -> str:
    """https://host[/base-path] – PUBLIC_URL if set, else what the request (or proxy) says."""
    if settings.public_url:
        return settings.public_url.rstrip("/")
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = host or request.headers.get("host") or request.url.netloc
    return f"{request.url.scheme}://{host}{settings.base_path}"
