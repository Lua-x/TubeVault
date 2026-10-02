"""Update yt-dlp at runtime without rebuilding the image.

The new version is installed into `/config/.runtime/python`, which the container puts in
front of the bundled packages via PYTHONPATH. A running process keeps the version it
started with; the new one is used after the next (re)start.
"""

from __future__ import annotations

import importlib.metadata
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

PACKAGES = ("yt-dlp", "yt-dlp-ejs")


@dataclass
class UpdateResult:
    updated: bool
    version: str | None
    message: str


def runtime_site_dir(runtime_dir: Path) -> Path:
    return runtime_dir / "python"


def current_ytdlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__

        return str(__version__)
    except ImportError:
        return None


def _version_in(path: Path) -> str | None:
    for dist in importlib.metadata.distributions(path=[str(path)]):
        if dist.metadata["Name"] and dist.metadata["Name"].lower() == "yt-dlp":
            return dist.version
    return None


def bundled_version(exclude: Path) -> str | None:
    paths = [p for p in sys.path if p and Path(p).resolve() != exclude.resolve()]
    for dist in importlib.metadata.distributions(path=paths):
        if dist.metadata["Name"] and dist.metadata["Name"].lower() == "yt-dlp":
            return dist.version
    return None


def _version_key(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", version))


def drop_outdated_runtime(runtime_dir: Path) -> None:
    """After an image update the bundled yt-dlp can be newer than the runtime copy."""
    site = runtime_site_dir(runtime_dir)
    if not site.exists():
        return
    runtime = _version_in(site)
    bundled = bundled_version(site)
    if runtime is None or _version_key(runtime) <= _version_key(bundled):
        log.info(
            "Runtime-yt-dlp (%s) ist nicht neuer als im Image (%s) – wird entfernt",
            runtime,
            bundled,
        )
        shutil.rmtree(site, ignore_errors=True)


def update_ytdlp(runtime_dir: Path, timeout: int = 300) -> UpdateResult:
    site = runtime_site_dir(runtime_dir)
    staging = site.with_name("python.new")
    shutil.rmtree(staging, ignore_errors=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    before = _version_in(site) if site.exists() else bundled_version(site)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--no-cache-dir",
        "--disable-pip-version-check",
        "--no-deps",
        "--upgrade",
        "--target",
        str(staging),
        *PACKAGES,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        shutil.rmtree(staging, ignore_errors=True)
        log.warning("yt-dlp-Update fehlgeschlagen: %s %s", exc, stderr.strip()[-500:])
        return UpdateResult(
            False, before, "Update fehlgeschlagen – die bisherige Version bleibt aktiv."
        )

    after = _version_in(staging)
    if after is None or _version_key(after) <= _version_key(before):
        shutil.rmtree(staging, ignore_errors=True)
        return UpdateResult(False, before, f"yt-dlp ist aktuell ({before}).")

    shutil.rmtree(site, ignore_errors=True)
    staging.rename(site)
    log.info("yt-dlp aktualisiert: %s → %s", before, after)
    return UpdateResult(True, after, f"yt-dlp aktualisiert: {before} → {after}")
