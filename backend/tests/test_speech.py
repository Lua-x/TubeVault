"""Subtitles from speech recognition: set up on demand, then made on this server."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import speech
from app.services.speech import Speech, SpeechError, Transcript
from app.speech_job import timestamp, to_vtt
from tests.conftest import add_and_wait
from tests.test_access import _login

FAKE_WHISPER = """
from types import SimpleNamespace
from pathlib import Path


class WhisperModel:
    def __init__(self, path, device, compute_type, cpu_threads):
        assert Path(path, "model.bin").is_file() and device == "cpu" and cpu_threads >= 1

    def transcribe(self, source, language=None, vad_filter=False, beam_size=5):
        assert Path(source).is_file() and vad_filter
        segments = [
            SimpleNamespace(start=0.0, end=1.5, text="  Hallo   Welt "),
            SimpleNamespace(start=1.5, end=2.0, text="   "),
            SimpleNamespace(start=3661.25, end=3662.0, text="Tschüss"),
        ]
        info = SimpleNamespace(language=language or "de", language_probability=0.98765)
        return iter(segments), info
"""


class FakeSpeech:
    """Stands in for pip, Hugging Face and the model."""

    def __init__(self) -> None:
        self.version: str | None = None
        self.models: set[str] = set()
        self.language = "de"
        self.text = "Hallo zusammen"
        self.fail_install: str | None = None
        self.calls: list[tuple[str, str | None]] = []

    def installed(self) -> str | None:
        return self.version

    def model_ready(self, size: str) -> bool:
        return size in self.models

    def ready(self, size: str) -> bool:
        return self.version is not None and size in self.models

    def install(self) -> str:
        if self.fail_install:
            raise SpeechError(self.fail_install)
        self.version = "1.2.1"
        return self.version

    def download_model(self, size: str) -> None:
        self.models.add(size)

    def transcribe(self, size: str, source: Path, target: Path, language: str | None) -> Transcript:
        self.calls.append((size, language))
        cues = f"00:00:00.000 --> 00:00:02.000\n{self.text}\n" if self.text else ""
        target.write_text(f"WEBVTT\n\n{cues}", encoding="utf-8")
        return Transcript(language or self.language, 0.9)

    def uninstall(self) -> None:
        self.version = None
        self.models.clear()

    def cancel(self) -> None:
        pass


def _ctx(client: TestClient) -> Any:
    return client.app.state.ctx  # type: ignore[attr-defined]


def _speech_subs(client: TestClient, video_id: int) -> list[dict[str, Any]]:
    subs = client.get(f"/api/videos/{video_id}").json()["subtitles"]
    return [s for s in subs if s["lang"].endswith("-x-asr")]


@pytest.fixture
def fake(admin: TestClient) -> FakeSpeech:
    engine = FakeSpeech()
    _ctx(admin).speech.speech = engine
    return engine


def test_vtt_from_segments() -> None:
    assert timestamp(0) == "00:00:00.000"
    assert timestamp(3661.2504) == "01:01:01.250"
    assert timestamp(-1) == "00:00:00.000"

    class Seg:
        def __init__(self, start: float, end: float, text: str) -> None:
            self.start, self.end, self.text = start, end, text

    vtt = to_vtt([Seg(0, 1.5, " Hallo\n Welt "), Seg(2, 3, "  ")])
    assert vtt == "WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHallo Welt\n"
    assert speech.speech_file(Path("/m/Urlaub [x].mp4"), "de") == Path(
        "/m/Urlaub [x].de.speech.vtt"
    )
    assert speech.is_speech(speech.speech_lang("de")) and not speech.is_speech("de")


def test_set_up_then_make_subtitles(admin: TestClient, fake: FakeSpeech) -> None:
    ctx = _ctx(admin)
    add_and_wait(admin, "speechvid01")
    video = admin.get("/api/videos").json()["items"][0]

    state = admin.get("/api/admin/speech").json()
    assert state["installed"] is None and state["ready"] is False and state["model"] == "base"
    assert [(m["size"], m["ready"]) for m in state["models"]] == [
        ("tiny", False),
        ("base", False),
        ("small", False),
    ]
    # Nothing happens before an admin sets it up.
    refused = admin.post(f"/api/videos/{video['id']}/subtitles/speech")
    assert refused.status_code == 409 and "eingerichtet" in refused.json()["detail"]
    assert admin.post("/api/admin/speech/missing").status_code == 409

    task = admin.post("/api/admin/speech/setup")
    assert task.status_code == 200 and task.json()["kind"] == "speech"
    ctx.library_tasks.wait()
    state = admin.get("/api/admin/speech").json()
    assert state["installed"] == "1.2.1" and state["ready"] is True

    # Made in the background.
    queued = admin.post(f"/api/videos/{video['id']}/subtitles/speech")
    assert queued.status_code == 202 and queued.json()["queued"] == 1
    assert admin.get("/api/admin/speech").json()["queued"] == 1
    assert ctx.speech.run_once() is True
    assert ctx.speech.run_once() is False
    assert fake.calls == [("base", None)]
    # An extra track next to the one from YouTube.
    assert len(admin.get(f"/api/videos/{video['id']}").json()["subtitles"]) == 2
    subs = _speech_subs(admin, video["id"])
    assert [(s["lang"], s["label"], s["is_auto"]) for s in subs] == [
        ("de-x-asr", "Deutsch (Spracherkennung)", True)
    ]
    track = admin.get(f"/api/videos/{video['id']}/subtitles/{subs[0]['id']}.vtt")
    assert track.status_code == 200 and "Hallo zusammen" in track.text
    first = next(ctx.settings.media_dir.rglob("*.de.speech.vtt"))

    # Again with a fixed language: the earlier subtitle is replaced, file and all.
    current = admin.get("/api/settings").json()
    admin.put("/api/settings", json={**current, "speech": {**current["speech"], "language": "en"}})
    admin.post(f"/api/videos/{video['id']}/subtitles/speech")
    ctx.speech.run_once()
    subs = _speech_subs(admin, video["id"])
    assert [s["lang"] for s in subs] == ["en-x-asr"] and fake.calls[-1] == ("base", "en")
    assert not first.exists()
    assert len(list(ctx.settings.media_dir.rglob("*.speech.vtt"))) == 1

    # Silence: reported, nothing attached, the old track stays.
    fake.text = ""
    admin.post(f"/api/videos/{video['id']}/subtitles/speech")
    ctx.speech.run_once()
    assert "Keine Sprache" in admin.get("/api/admin/speech").json()["last_error"]
    assert len(_speech_subs(admin, video["id"])) == 1

    # Deleting the video takes the file along.
    admin.delete(f"/api/videos/{video['id']}")
    assert not list(ctx.settings.media_dir.rglob("*.speech.vtt"))


def test_only_admins_and_failures_are_told(admin: TestClient, fake: FakeSpeech) -> None:
    ctx = _ctx(admin)
    add_and_wait(admin, "speechvid02")
    video = admin.get("/api/videos").json()["items"][0]
    viewer = _login(admin, "gast")
    assert viewer.get("/api/admin/speech").status_code == 403
    assert viewer.post("/api/admin/speech/setup").status_code == 403
    assert viewer.post(f"/api/videos/{video['id']}/subtitles/speech").status_code == 403

    fake.fail_install = "Keine Verbindung – ist der Server online?"
    admin.post("/api/admin/speech/setup")
    ctx.library_tasks.wait()
    task = ctx.library_tasks.current
    assert task.state == "failed" and "Verbindung" in (task.message or "")
    assert admin.get("/api/admin/speech").json()["installed"] is None

    # Bad settings are refused.
    current = admin.get("/api/settings").json()
    for bad in ({"model": "large"}, {"language": "deutsch"}):
        body = {**current, "speech": {**current["speech"], **bad}}
        assert admin.put("/api/settings", json=body).status_code == 422

    # Removing frees the space again.
    fake.fail_install = None
    admin.post("/api/admin/speech/setup")
    ctx.library_tasks.wait()
    assert admin.get("/api/admin/speech").json()["ready"] is True
    removed = admin.delete("/api/admin/speech")
    assert removed.status_code == 200 and removed.json()["installed"] is None

    # Choosing another model in the settings sets up and uses that one.
    admin.post("/api/admin/speech/setup", json={"model": "tiny"})
    ctx.library_tasks.wait()
    state = admin.get("/api/admin/speech").json()
    assert state["model"] == "tiny" and state["ready"] is True
    assert admin.get("/api/settings").json()["speech"]["model"] == "tiny"
    assert admin.post("/api/admin/speech/setup", json={"model": "huge"}).status_code == 422


def _own_video(admin: TestClient, tmp_path: Path) -> None:
    ctx = _ctx(admin)
    ctx.importer.import_dir = tmp_path / "import"
    folder = ctx.importer.import_dir / "Urlaub"
    folder.mkdir(parents=True)
    (folder / "Strand.mp4").write_bytes(b"\x00" * 4096)
    admin.post("/api/import/scan")
    ctx.library_tasks.wait()
    keys = [c["key"] for c in admin.get("/api/import").json()["candidates"]]
    admin.post("/api/import/run", json={"keys": keys, "mode": "move"})
    ctx.library_tasks.wait()


def test_own_videos(admin: TestClient, fake: FakeSpeech, tmp_path: Path) -> None:
    ctx = _ctx(admin)
    fake.version, fake.models = "1.2.1", {"base"}
    current = admin.get("/api/settings").json()
    admin.put(
        "/api/settings", json={**current, "speech": {**current["speech"], "auto_own_videos": True}}
    )
    _own_video(admin, tmp_path)
    # Imported without subtitles: queued by itself.
    state = admin.get("/api/admin/speech").json()
    assert state["queued"] == 1 and state["missing"] == 1
    assert ctx.speech.run_once() is True
    state = admin.get("/api/admin/speech").json()
    assert state["missing"] == 0 and state["queued"] == 0
    # "Alle erkennen" finds nothing left to do.
    assert admin.post("/api/admin/speech/missing").json() == {"queued": 0}


def _fake_install(site: Path, model: Path) -> None:
    (site / "faster_whisper").mkdir(parents=True)
    (site / "faster_whisper" / "__init__.py").write_text(textwrap.dedent(FAKE_WHISPER))
    dist = site / "faster_whisper-1.2.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: faster-whisper\nVersion: 1.2.1\n")
    model.mkdir(parents=True)
    for name in speech.MODEL_FILES:
        (model / name).write_text("x")


def test_the_real_process(tmp_path: Path) -> None:
    """The job runs as its own Python process with the packages from /config/.runtime."""
    engine = Speech(Settings(config_dir=tmp_path / "config", media_dir=tmp_path / "media"))
    assert engine.installed() is None and not engine.ready("tiny")
    _fake_install(engine.site_dir, engine.model_dir("tiny"))
    assert engine.installed() == "1.2.1" and engine.ready("tiny")

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"\x00")
    target = tmp_path / "clip.vtt"
    result = engine.transcribe("tiny", source, target, None)
    assert result == Transcript("de", 0.988)
    assert target.read_text(encoding="utf-8") == (
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHallo Welt\n\n"
        "01:01:01.250 --> 01:01:02.000\nTschüss\n"
    )
    assert engine.transcribe("tiny", source, target, "fr").language == "fr"
    # A broken run says why, without taking anything down.
    with pytest.raises(SpeechError):
        engine.transcribe("tiny", tmp_path / "missing.mp4", target, None)
    engine.uninstall()
    assert engine.installed() is None and not engine.model_ready("tiny")


def test_downloads_stay_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Speech(Settings(config_dir=tmp_path / "config", media_dir=tmp_path / "media"))
    seen: list[tuple[list[str], dict[str, str]]] = []

    def run(command: list[str], timeout: int, env: dict[str, str]) -> str:
        seen.append((command, env))
        if "pip" in command:
            staging = Path(command[command.index("--target") + 1])
            _fake_install(staging, tmp_path / "unused")
        if "download" in command:
            target = Path(command[command.index("--target") + 1])
            (target / ".cache").mkdir(parents=True)
            for name in speech.MODEL_FILES:
                (target / name).write_text("x")
        return '{"language": "de", "probability": 1}\n'

    monkeypatch.setattr(engine, "_run", run)
    assert engine.install() == "1.2.1"
    engine.download_model("small")
    assert engine.model_ready("small") and not (engine.model_dir("small") / ".cache").exists()
    pip, download = seen
    assert "faster-whisper>=1.1,<2" in pip[0] and "--only-binary=:all:" in pip[0]
    assert download[1]["HF_HUB_DISABLE_TELEMETRY"] == "1" and "HF_HUB_OFFLINE" not in download[1]
    engine.transcribe("small", tmp_path / "a.mp4", tmp_path / "a.vtt", None)
    # Recognition itself never goes online.
    assert seen[-1][1]["HF_HUB_OFFLINE"] == "1"
    assert speech._friendly("OSError: [Errno 28] No space left on device") == (
        "Kein Platz mehr auf dem Laufwerk."
    )
    assert "Verbindung" in speech._friendly("requests.exceptions.ConnectionError: boom")


def test_secrets_stay_with_the_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "geheim")
    monkeypatch.setenv("ADMIN_PASSWORD", "geheim")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    engine = Speech(Settings(config_dir=tmp_path / "config", media_dir=tmp_path / "media"))
    script = "import json, os; print(json.dumps(dict(os.environ)))"
    seen = json.loads(engine._run([sys.executable, "-c", script], 30, {"EXTRA": "1"}))
    assert "OIDC_CLIENT_SECRET" not in seen and "ADMIN_PASSWORD" not in seen
    assert seen["HTTPS_PROXY"] == "http://proxy:3128" and seen["EXTRA"] == "1"
