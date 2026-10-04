"""Speech recognition, run as its own process: `python -m app.speech_job …`.

Kept apart from the server on purpose: the model only takes memory while it works, a
crash can't take the server down, and faster-whisper (installed on demand into
/config/.runtime/speech) never has to be importable by the server itself. Only the
standard library is used here besides faster-whisper and huggingface_hub.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


class Segment(Protocol):
    start: float
    end: float
    text: str


def timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def to_vtt(segments: Iterable[Segment]) -> str:
    cues = ["WEBVTT", ""]
    for segment in segments:
        text = " ".join(segment.text.split())
        if not text:
            continue
        cues += [f"{timestamp(segment.start)} --> {timestamp(segment.end)}", text, ""]
    return "\n".join(cues)


def transcribe(
    model_dir: Path, source: Path, target: Path, language: str | None
) -> dict[str, object]:
    from faster_whisper import WhisperModel

    # Half the cores: playback and conversions on the same server stay smooth.
    threads = max(1, (os.cpu_count() or 2) // 2)
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = model.transcribe(str(source), language=language, vad_filter=True, beam_size=5)
    target.write_text(to_vtt(segments), encoding="utf-8")
    return {"language": info.language, "probability": round(info.language_probability, 3)}


def download(size: str, target: Path) -> dict[str, object]:
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=f"Systran/faster-whisper-{size}", local_dir=str(target))
    return {"model": size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.speech_job")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("transcribe")
    run.add_argument("--model", type=Path, required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--language", default=None)
    fetch = commands.add_parser("download")
    fetch.add_argument("--size", choices=("tiny", "base", "small"), required=True)
    fetch.add_argument("--target", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "transcribe":
        result = transcribe(args.model, args.input, args.output, args.language)
    else:
        result = download(args.size, args.target)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
