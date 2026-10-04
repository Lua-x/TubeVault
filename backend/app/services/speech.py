"""Subtitles from speech recognition (faster-whisper), on this server, on demand.

Neither the program nor a model is part of the image. Only when an admin clicks
"Einrichten" is faster-whisper installed from PyPI into `/config/.runtime/speech` and the
model fetched from Hugging Face into `/config/models` – or the model is put there by hand.
Recognition itself runs offline, in its own low-priority process (app/speech_job.py).
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import Settings

log = logging.getLogger(__name__)

ModelSize = Literal["tiny", "base", "small"]
# Download sizes in MB (int8 is computed from these on load).
MODELS: dict[str, int] = {"tiny": 75, "base": 145, "small": 485}
PACKAGE = "faster-whisper>=1.1,<2"
# Speech subtitles get a private-use language tag ("de-x-asr"), so they never collide
# with subtitles from YouTube or the file, and are easy to find again.
SPEECH_TAG = "-x-asr"
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")

INSTALL_TIMEOUT_S = 1800
DOWNLOAD_TIMEOUT_S = 3600
TRANSCRIBE_TIMEOUT_S = 6 * 3600

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
# What the child processes may see of the server's environment – no passwords, no
# client secrets: pip and Hugging Face only need paths, locale and proxy settings.
_PASSED_ENV = re.compile(
    r"^(PATH|HOME|LANG|LC_\w+|TZ|TMPDIR|XDG_CACHE_HOME|SSL_CERT_\w+|REQUESTS_CA_BUNDLE"
    r"|PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|PIP_TRUSTED_HOST|PIP_CERT"
    r"|(HTTPS?|NO|ALL)_PROXY|(https?|no|all)_proxy)$"
)


class SpeechError(Exception):
    """Something the admin should read, in German."""


@dataclass(frozen=True)
class Transcript:
    language: str
    probability: float


def speech_lang(language: str) -> str:
    return f"{language}{SPEECH_TAG}"


def is_speech(lang: str) -> bool:
    return lang.endswith(SPEECH_TAG)


def speech_file(video_file: Path, language: str) -> Path:
    """`Title [id].de.speech.vtt` – media servers still read "de" from the name."""
    return video_file.with_name(f"{video_file.stem}.{language}.speech.vtt")


def _nice() -> list[str]:
    nice = shutil.which("nice")
    return [nice, "-n", "19"] if nice else []


def _last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][-300:] if lines else ""


class Speech:
    """Where the program and models live, and the processes that use them."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    # --- places --------------------------------------------------------------------------

    @property
    def site_dir(self) -> Path:
        return self._settings.runtime_dir / "speech"

    @property
    def models_dir(self) -> Path:
        return self._settings.config_dir / "models"

    def model_dir(self, size: str) -> Path:
        return self.models_dir / f"faster-whisper-{size}"

    # --- state ---------------------------------------------------------------------------

    def installed(self) -> str | None:
        """The installed faster-whisper version, if any."""
        if not self.site_dir.is_dir():
            return None
        for dist in importlib.metadata.distributions(path=[str(self.site_dir)]):
            name = dist.metadata["Name"] or ""
            if name.lower().replace("_", "-") == "faster-whisper":
                return dist.version
        return None

    def model_ready(self, size: str) -> bool:
        folder = self.model_dir(size)
        return all((folder / name).is_file() for name in MODEL_FILES)

    def ready(self, size: str) -> bool:
        return self.installed() is not None and self.model_ready(size)

    # --- setting up ----------------------------------------------------------------------

    def install(self) -> str:
        """pip into a staging folder, then swap it in – a failed attempt changes nothing."""
        staging = self.site_dir.with_name("speech.new")
        shutil.rmtree(staging, ignore_errors=True)
        self.site_dir.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "--timeout",
            "30",
            "--retries",
            "2",
            # Wheels only: nothing is built, no setup.py of some package runs.
            "--only-binary=:all:",
            "--target",
            str(staging),
            PACKAGE,
        ]
        try:
            self._run(command, INSTALL_TIMEOUT_S, env={"PYTHONPATH": ""})
        except SpeechError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        shutil.rmtree(self.site_dir, ignore_errors=True)
        staging.rename(self.site_dir)
        version = self.installed()
        log.info("Spracherkennung installiert: faster-whisper %s", version)
        return version or "?"

    def download_model(self, size: str) -> None:
        if size not in MODELS:
            raise SpeechError(f"Unbekanntes Modell: {size}")
        target = self.model_dir(size)
        partial = target.with_name(f"{target.name}.partial")
        partial.mkdir(parents=True, exist_ok=True)  # kept: a second try resumes
        self._job(
            ["download", "--size", size, "--target", str(partial)],
            DOWNLOAD_TIMEOUT_S,
            offline=False,
        )
        # Hugging Face's own bookkeeping isn't needed for loading.
        shutil.rmtree(partial / ".cache", ignore_errors=True)
        if not all((partial / name).is_file() for name in MODEL_FILES):
            raise SpeechError("Das Modell ist unvollständig angekommen – bitte noch einmal.")
        shutil.rmtree(target, ignore_errors=True)
        partial.rename(target)
        log.info("Sprachmodell %s geladen", size)

    def uninstall(self) -> None:
        shutil.rmtree(self.site_dir, ignore_errors=True)
        for size in MODELS:
            shutil.rmtree(self.model_dir(size), ignore_errors=True)
            shutil.rmtree(
                self.model_dir(size).with_name(f"{self.model_dir(size).name}.partial"),
                ignore_errors=True,
            )
        log.info("Spracherkennung entfernt")

    # --- recognising ---------------------------------------------------------------------

    def transcribe(self, size: str, source: Path, target: Path, language: str | None) -> Transcript:
        if not self.ready(size):
            raise SpeechError("Die Spracherkennung ist noch nicht eingerichtet.")
        args = ["transcribe", "--model", str(self.model_dir(size))]
        args += ["--input", str(source), "--output", str(target)]
        if language:
            args += ["--language", language]
        output = self._job(args, TRANSCRIBE_TIMEOUT_S, offline=True)
        try:
            result = json.loads(output.strip().splitlines()[-1])
            return Transcript(str(result["language"]), float(result["probability"]))
        except (ValueError, KeyError, IndexError) as exc:
            raise SpeechError("Die Spracherkennung hat nichts Lesbares zurückgegeben.") from exc

    def cancel(self) -> None:
        """Stops a running process (on shutdown)."""
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    # --- processes -----------------------------------------------------------------------

    def _job(self, args: list[str], timeout: int, *, offline: bool) -> str:
        env = {
            # The speech packages first, then the backend for `app.speech_job`.
            "PYTHONPATH": os.pathsep.join([str(self.site_dir), str(_BACKEND_ROOT)]),
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HOME": str(self._settings.config_dir / ".cache" / "huggingface"),
        }
        if offline:
            env["HF_HUB_OFFLINE"] = "1"  # recognition never goes online
        return self._run([*_nice(), sys.executable, "-m", "app.speech_job", *args], timeout, env)

    def _run(self, command: list[str], timeout: int, env: dict[str, str]) -> str:
        environment = {k: v for k, v in os.environ.items() if _PASSED_ENV.match(k)}
        environment.update(env)
        try:
            process = subprocess.Popen(  # noqa: S603 – our interpreter, our arguments
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=_BACKEND_ROOT,
                env=environment,
            )
        except OSError as exc:
            raise SpeechError(f"Konnte nicht gestartet werden: {exc}") from exc
        with self._lock:
            self._process = process
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise SpeechError("Hat zu lange gedauert und wurde abgebrochen.") from exc
        finally:
            with self._lock:
                self._process = None
        if process.returncode != 0:
            detail = _last_line(stderr)
            log.warning("Spracherkennung: %s fehlgeschlagen: %s", command[-1], stderr[-2000:])
            raise SpeechError(_friendly(detail) or "Ist fehlgeschlagen (siehe Log).")
        return stdout


def _friendly(detail: str) -> str:
    """The last error line, with the usual suspects said in plain words."""
    lowered = detail.lower()
    if re.search(r"connection|resolve|network|timed out|unreachable|proxy", lowered):
        return "Keine Verbindung – ist der Server online?"
    if "no space" in lowered:
        return "Kein Platz mehr auf dem Laufwerk."
    if "memory" in lowered:
        return "Zu wenig Arbeitsspeicher – ein kleineres Modell hilft."
    return detail
