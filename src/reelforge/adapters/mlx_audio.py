"""mlx-audio adapter: presence check, worker selftest, batch text-to-speech and ffmpeg clean-up.

The model runs in `tts_worker.py`, a standalone script started once per batch inside the
mlx-audio uv environment. This module never imports mlx-audio.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import re
import subprocess
import sys
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reelforge.adapters.base import AdapterError, CancelToken, HealthReport, ProgressCb
from reelforge.adapters.runner import run_command

WORKER_PATH: Path = Path(__file__).with_name("tts_worker.py")

SPEED_MIN = 0.8
SPEED_MAX = 1.25
PAUSE_MIN = 0.0
PAUSE_MAX = 1.0

TARGET_LUFS = -16.0
OUT_RATE = 48000
PEAK_LIMIT = 0.89

# The `voice_model` setting maps to the models.toml key.
VOICE_MODELS: dict[str, str] = {"omnivoice": "tts", "kokoro": "tts_fallback"}


@dataclass(frozen=True)
class VoicePreset:
    id: str
    label: str
    voice: str


PRESETS: dict[str, list[VoicePreset]] = {
    "kokoro": [
        VoicePreset("hf_alpha", "Hindi female (Alpha)", "hf_alpha"),
        VoicePreset("hf_beta", "Hindi female (Beta)", "hf_beta"),
        VoicePreset("hm_omega", "Hindi male (Omega)", "hm_omega"),
        VoicePreset("hm_psi", "Hindi male (Psi)", "hm_psi"),
    ],
    "omnivoice": [
        VoicePreset("asha", "Asha (female)", "A warm adult Indian woman, clear and expressive"),
        VoicePreset("ravi", "Ravi (male)", "A friendly adult Indian man, clear and steady"),
    ],
}


def check_speed(speed: float) -> float:
    if not (SPEED_MIN <= speed <= SPEED_MAX):
        raise ValueError("speed must be between 0.8 and 1.25")
    return speed


def check_pause(name: str, value: float) -> float:
    if not (PAUSE_MIN <= value <= PAUSE_MAX):
        raise ValueError(f"{name} must be between 0 and 1 seconds")
    return value


def plan_speed(voice_model: str, speed: float) -> tuple[float, float | None]:
    """Return `(worker_speed, atempo)`: Kokoro has a native speed, OmniVoice uses ffmpeg."""
    check_speed(speed)
    if voice_model == "kokoro":
        return speed, None
    return 1.0, speed


@dataclass
class VoiceLine:
    id: str
    text: str
    voice: str | None
    ref_audio: Path | None
    ref_text: str | None
    speed: float
    lang: str = "hi"


@dataclass
class VoiceResult:
    id: str
    path: Path | None
    duration_s: float | None
    error: str | None


_LUFS_RE = re.compile(r"I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS")
_TRIM = (
    "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.02,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.02,"
    "areverse"
)


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def _last_line(text: str) -> str:
    return _first_line("\n".join(reversed(text.splitlines())))


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


NO_RUBBERBAND = (
    'ffmpeg is missing the "rubberband" filter, needed for pitch and tempo changes. '
    "Install ffmpeg-full."
)


def ffmpeg_has_filter(name: str) -> bool:
    """Whether the installed ffmpeg lists the filter `name` (asked every time, never cached)."""
    try:
        res = subprocess.run(  # noqa: S603
            ["ffmpeg", "-hide_banner", "-filters"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(len(parts := ln.split()) >= 2 and parts[1] == name for ln in res.stdout.splitlines())


async def postprocess_wav(
    src: Path,
    dst: Path,
    *,
    atempo: float | None = None,
    semitones: float = 0.0,
    tempo: float = 1.0,
    gain_db: float = 0.0,
    timeout_s: float = 120.0,
    cancel: CancelToken | None = None,
) -> float:
    """Trim edge silence, change tempo and pitch, normalise to -16 LUFS, apply `gain_db` after
    the normalisation, and write a 48 kHz mono 16-bit WAV."""
    chain = _TRIM
    if atempo is not None and atempo != 1.0:
        chain += f",atempo={atempo:.4f}"
    if semitones != 0.0 or tempo != 1.0:
        if not ffmpeg_has_filter("rubberband"):
            raise AdapterError(NO_RUBBERBAND)
        chain += f",rubberband=pitch={2 ** (semitones / 12):.6f}:tempo={tempo:.6f}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    measure = await run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(src),
            "-af",
            f"{chain},ebur128",
            "-f",
            "null",
            "-",
        ],
        timeout_s=timeout_s,
        cancel=cancel,
    )
    _check(measure, "ffmpeg loudness measurement")
    found = _LUFS_RE.findall(measure.stderr)
    gain = 0.0
    if found and found[-1] != "-inf":
        gain = TARGET_LUFS - float(found[-1])
    gain += gain_db
    final = (
        f"{chain},volume={gain:.3f}dB,alimiter=limit={PEAK_LIMIT}:level=disabled,"
        f"aresample={OUT_RATE}"
    )
    res = await run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(src),
            "-af",
            final,
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        timeout_s=timeout_s,
        cancel=cancel,
    )
    _check(res, "ffmpeg post-processing")
    try:
        duration = _wav_seconds(dst)
    except (OSError, wave.Error, EOFError) as exc:
        raise AdapterError(f"ffmpeg produced no usable audio: {exc}") from exc
    if duration <= 0 or math.isnan(duration):
        raise AdapterError("ffmpeg produced empty audio")
    return duration


def _check(res: Any, what: str) -> None:
    if res.cancelled:
        raise AdapterError("cancelled")
    if res.timed_out or res.exit_code != 0:
        detail = _last_line(res.stderr) or res.error or "unknown error"
        raise AdapterError(f"{what} failed: {detail}")


class MlxAudioAdapter:
    name = "mlx_audio"

    def __init__(
        self,
        project_path: Path | None,
        *,
        backend: Literal["mock", "real"] = "real",
        timeout_s: float = 600.0,
    ) -> None:
        self.project_path = project_path
        self.backend = backend
        self.timeout_s = timeout_s

    def check(self) -> HealthReport:
        if self.project_path is None:
            return HealthReport(name=self.name, ok=False, detail="mlx-audio path is not configured")
        if not self.project_path.is_dir():
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"mlx-audio project not found at {self.project_path}",
            )
        if not (self.project_path / ".venv").is_dir():
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"mlx-audio has no virtual environment in {self.project_path}",
            )
        return HealthReport(name=self.name, ok=True, detail=f"mlx-audio at {self.project_path}")

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)

    def _python(self) -> str:
        if self.backend == "mock":
            return sys.executable
        if self.project_path is None:
            raise AdapterError("mlx-audio path is not configured")
        return str(self.project_path / ".venv" / "bin" / "python")

    def selftest(self, timeout_s: float = 120.0, model_id: str | None = None) -> HealthReport:
        """Run `tts_worker.py --selftest` in the mlx-audio environment."""

        def failed(reason: str) -> HealthReport:
            return HealthReport(
                name=self.name, ok=False, detail=f"tts_worker selftest failed: {reason}"
            )

        try:
            argv = [self._python(), str(WORKER_PATH), "--selftest"]
        except AdapterError as exc:
            return failed(str(exc))
        if self.backend == "mock":
            argv += ["--backend", "mock"]
        if model_id:
            argv += ["--model", model_id]
        try:
            res = subprocess.run(  # noqa: S603
                argv, capture_output=True, text=True, timeout=timeout_s, check=False
            )
        except subprocess.TimeoutExpired:
            return failed(f"timed out after {timeout_s:g}s")
        except OSError as exc:
            return failed(str(exc))
        if res.returncode != 0:
            return failed(_first_line(res.stderr) or f"exit code {res.returncode}")
        return HealthReport(name=self.name, ok=True, detail="tts_worker selftest passed")

    async def run_batch(
        self,
        lines: list[VoiceLine],
        model_id: str,
        voice_model: str,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        on_line: Callable[[VoiceResult], None] | None = None,
        job_id: str | None = None,
    ) -> list[VoiceResult]:
        plans = {ln.id: plan_speed(voice_model, ln.speed) for ln in lines}
        raw_dir = out_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        batch = out_dir / "batch.jsonl"
        rows = [
            {
                "id": ln.id,
                "text": ln.text,
                "model": model_id,
                "voice": ln.voice,
                "ref_audio": str(ln.ref_audio) if ln.ref_audio else None,
                "ref_text": ln.ref_text,
                "speed": plans[ln.id][0],
                "lang": ln.lang,
            }
            for ln in lines
        ]
        batch.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")
        argv = [
            self._python(), str(WORKER_PATH), "--batch", str(batch), "--out-dir", str(raw_dir),
            "--backend", self.backend,
        ]  # fmt: skip

        total = len(lines)
        results: dict[str, VoiceResult] = {}
        events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def on_stdout(text: str) -> None:
            if not text.strip():
                return
            try:
                event = json.loads(text)
            except ValueError:
                return
            if isinstance(event, dict) and "id" in event:
                events.put_nowait(event)  # type: ignore[reportUnknownArgumentType]

        async def finish(event: dict[str, Any]) -> None:
            line_id = str(event["id"])
            if line_id not in plans or line_id in results:
                return
            if "error" in event:
                result = VoiceResult(line_id, None, None, str(event["error"]))
            else:
                try:
                    dst = out_dir / f"{line_id}.48k.wav"
                    duration = await postprocess_wav(
                        Path(str(event["path"])), dst, atempo=plans[line_id][1], cancel=cancel
                    )
                    result = VoiceResult(line_id, dst, duration, None)
                except AdapterError as exc:
                    if cancel.cancelled:
                        raise
                    result = VoiceResult(line_id, None, None, str(exc))
            results[line_id] = result
            if on_line:
                on_line(result)
            progress(round(100 * len(results) / max(total, 1)), f"line {len(results)} of {total}")

        async def consume() -> None:
            while (event := await events.get()) is not None:
                await finish(event)

        consumer = asyncio.create_task(consume())
        try:
            cmd = await run_command(
                argv,
                timeout_s=self.timeout_s,
                cancel=cancel,
                job_id=job_id,
                on_stdout_line=on_stdout,
            )
        finally:
            events.put_nowait(None)
        try:
            await consumer
        except AdapterError:
            raise
        finally:
            if not consumer.done():
                consumer.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await consumer
        if cmd.cancelled or cancel.cancelled:
            raise AdapterError("cancelled")
        if cmd.timed_out or cmd.exit_code != 0:
            reason = cmd.error if cmd.timed_out else None
            reason = reason or _last_line(cmd.stderr)
            reason = reason or cmd.error or f"exit code {cmd.exit_code}"
            raise AdapterError(f"Voice engine stopped: {reason}")
        ordered: list[VoiceResult] = []
        for ln in lines:
            got = results.get(ln.id)
            if got is None:
                got = VoiceResult(ln.id, None, None, "The voice engine produced no audio.")
                if on_line:
                    on_line(got)
            ordered.append(got)
        return ordered
