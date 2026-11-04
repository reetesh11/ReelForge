"""Word timing for captions, behind an `Aligner` protocol."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from typing import Protocol

from reelforge.adapters.runner import run_command
from reelforge.assembly import ffmpeg
from reelforge.assembly.captions import WordTiming
from reelforge.config import Settings
from reelforge.models_registry import load_models

WORKER_PATH: Path = Path(__file__).resolve().parent.parent / "adapters" / "align_worker.py"
ALIGN_MODEL_KEY = "align"


class AlignmentError(Exception):
    """Word timing failed; the caption falls back to line-level timing."""


class Aligner(Protocol):
    async def align(self, audio: Path, text: str, language: str) -> list[WordTiming]: ...


def aligner_id(aligner: object) -> str:
    return str(getattr(aligner, "id", type(aligner).__name__))


def _clip_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError):
        try:
            return ffmpeg.media_duration(path, "audio")
        except (ValueError, OSError) as exc:
            raise AlignmentError(f"cannot read the clip length: {exc}") from None


class ProportionalAligner:
    """Mock backend: split the clip across the words by character count. Deterministic."""

    id = "proportional"

    async def align(self, audio: Path, text: str, language: str) -> list[WordTiming]:
        del language
        words = text.split()
        if not words:
            return []
        total = _clip_seconds(audio)
        weight = sum(len(w) for w in words)
        out: list[WordTiming] = []
        cursor = 0.0
        for i, word in enumerate(words):
            end = total if i == len(words) - 1 else cursor + total * len(word) / weight
            out.append(WordTiming(word, round(cursor, 3), round(end, 3)))
            cursor = end
        return out


class MlxWhisperAligner:
    """Whisper word timestamps through mlx-audio, run by `adapters/align_worker.py`."""

    id = "mlx-whisper"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _python(self) -> str:
        if self.settings.backend == "mock" or self.settings.mlx_audio_path is None:
            return sys.executable
        return str(self.settings.mlx_audio_path / ".venv" / "bin" / "python")

    async def align(self, audio: Path, text: str, language: str) -> list[WordTiming]:
        try:
            model = load_models(self.settings.models_path).get(ALIGN_MODEL_KEY).id
        except (KeyError, OSError) as exc:
            raise AlignmentError(f"no alignment model is configured: {exc}") from None
        argv = [
            self._python(),
            str(WORKER_PATH),
            "--audio",
            str(audio),
            "--text",
            text,
            "--language",
            language,
            "--model",
            model,
        ]
        res = await run_command(argv, timeout_s=self.settings.command_timeout_s)
        if res.exit_code != 0:
            tail = [ln for ln in res.stderr.splitlines() if ln.strip()]
            raise AlignmentError(tail[-1] if tail else (res.error or "the aligner failed"))
        try:
            rows = json.loads(res.stdout.strip().splitlines()[-1])
            return [
                WordTiming(str(r["text"]), float(r["start_s"]), float(r["end_s"])) for r in rows
            ]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AlignmentError("the aligner returned an unreadable result") from None
