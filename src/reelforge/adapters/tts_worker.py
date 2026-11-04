"""Standalone text-to-speech worker.

This script runs inside the mlx-audio uv environment, so it must not import `reelforge`.
It reads a batch of lines (JSONL), loads each distinct model once, writes one 24 kHz mono
16-bit WAV per line, and prints one JSON progress line per finished line on stdout.

    python tts_worker.py --batch BATCH.jsonl --out-dir DIR [--backend real|mock]
    python tts_worker.py --selftest [--backend real|mock] [--model ID]

Batch line: {"id", "text", "model", "voice", "ref_audio", "ref_text", "speed", "lang"} plus the
optional {"instruct", "duration_scale", "target_speed", "gen"}. For OmniVoice the length target is
`estimated length x duration_scale / target_speed` seconds, passed to the model as `duration_s`
only when that factor is not 1.0.
Progress line: {"id", "path", "duration_s"[, "duration_requested_s"]} or {"id", "error"}.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

OUT_RATE = 24000
SILENCE_S = 0.3
FAIL_MARK = "[[fail]]"
SELFTEST_WORD = "नमस्ते"
KOKORO_LANG = {"hi": "h"}
TARGET_MIN_S = 0.3
TARGET_MAX_S = 60.0

# A synth returns (samples, rate) or (samples, rate, duration_requested_s).
Synth = Callable[[dict[str, Any]], tuple[Any, ...]]
LoadModel = Callable[[str], Synth]
Emit = Callable[[dict[str, Any]], None]


def _print_json(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def resample(
    samples: np.ndarray[Any, Any], rate: int, target: int = OUT_RATE
) -> np.ndarray[Any, Any]:
    """Linear-interpolation resample to `target` Hz (good enough before ffmpeg post-processing)."""
    if rate == target or samples.size == 0:
        return samples
    n_out = max(1, round(samples.size * target / rate))
    x_old = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype("float32")


def write_wav(path: Path, samples: np.ndarray[Any, Any], rate: int = OUT_RATE) -> float:
    """Write mono 16-bit PCM and return the duration in seconds."""
    clipped = np.clip(np.asarray(samples, dtype="float64"), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return float(pcm.size) / rate


def duration_factor(line: dict[str, Any]) -> float:
    """`duration_scale / target_speed` of a batch line (1.0 when neither key is given)."""
    scale = float(line.get("duration_scale") or 1.0)
    target = float(line.get("target_speed") or 1.0)
    return scale / target


def check_target(seconds: float) -> float:
    """The real model accepts 0.3 to 60 s; the mock mirrors that limit."""
    if not TARGET_MIN_S <= seconds <= TARGET_MAX_S:
        raise ValueError(
            f"Duration target {seconds:g} s is outside what the model accepts "
            f"({TARGET_MIN_S:g} to {TARGET_MAX_S:g} s)."
        )
    return seconds


def _mock_synth(line: dict[str, Any]) -> tuple[Any, ...]:
    text = str(line.get("text", ""))
    if FAIL_MARK in text:
        raise RuntimeError("mock failure requested by [[fail]]")
    speed = float(line.get("speed") or 1.0)
    words = len(text.split())
    tone_s = (0.3 + 0.25 * words) / speed
    factor = duration_factor(line)
    requested: float | None = None
    if factor != 1.0:
        tone_s = requested = check_target(tone_s * factor)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    freq = 180.0 + (int.from_bytes(digest[:2], "big") % 240)
    n_tone = round(tone_s * OUT_RATE)
    t = np.arange(n_tone) / OUT_RATE
    tone = 0.5 * np.sin(2 * np.pi * freq * t)
    fade = min(n_tone // 2, round(0.01 * OUT_RATE))
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade)
        tone[:fade] *= ramp
        tone[-fade:] *= ramp[::-1]
    gap = np.zeros(round(SILENCE_S * OUT_RATE))
    audio = np.concatenate([gap, tone, gap]).astype("float32")
    return (audio, OUT_RATE) if requested is None else (audio, OUT_RATE, requested)


def _mock_loader(_model_id: str) -> Synth:
    return _mock_synth


def _unshadow_mlx_audio() -> None:
    """Keep this folder off the import path before importing the real `mlx_audio`.

    Run as a script, Python puts this file's folder first on `sys.path`, where the
    ReelForge adapter `mlx_audio.py` would hide the real mlx-audio package.
    """
    here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]
    loaded = sys.modules.get("mlx_audio")
    if (
        loaded is not None
        and Path(getattr(loaded, "__file__", None) or "").resolve().parent == here
    ):
        del sys.modules["mlx_audio"]


def _real_loader(model_id: str) -> Synth:
    """Load an mlx-audio model lazily; the import happens only for the real backend."""
    _unshadow_mlx_audio()
    utils: Any = importlib.import_module("mlx_audio.tts.utils")
    model: Any = utils.load_model(model_id)
    is_kokoro = "kokoro" in model_id.lower()
    is_omnivoice = "omnivoice" in model_id.lower()

    def estimated_s(text: str) -> float:
        """OmniVoice's own default length for `text`, in seconds."""
        module: Any = importlib.import_module("mlx_audio.tts.models.omnivoice.duration")
        tokens: float = module.RuleDurationEstimator().estimate_duration(
            text, "Nice to meet you.", 25
        )
        per_second = int(model.sample_rate) / 960
        return max(10, int(tokens * 1.15)) / per_second

    def synth(line: dict[str, Any]) -> tuple[Any, ...]:
        kwargs: dict[str, Any] = {"text": line["text"]}
        if not is_omnivoice:  # the MLX OmniVoice build ignores `speed`; pace is `duration_s`
            kwargs["speed"] = float(line.get("speed") or 1.0)
        if is_omnivoice:
            # A voice description and the line's style values are one `instruct` string.
            parts = [str(p) for p in (line.get("voice"), line.get("instruct")) if p]
            if parts:
                kwargs["instruct"] = ", ".join(parts)
        elif line.get("voice"):
            kwargs["voice"] = line["voice"]
        requested: float | None = None
        factor = duration_factor(line) if is_omnivoice else 1.0
        if factor != 1.0:
            requested = check_target(estimated_s(str(line["text"])) * factor)
            kwargs["duration_s"] = requested
        gen: dict[str, Any] = dict(line.get("gen") or {})
        kwargs.update(gen)
        lang = str(line.get("lang") or "hi")
        if is_kokoro:
            kwargs["lang_code"] = KOKORO_LANG.get(lang, lang)
        else:
            kwargs["lang_code"] = lang
        if line.get("ref_audio"):
            kwargs["ref_audio"] = str(line["ref_audio"])
            kwargs["ref_text"] = line.get("ref_text") or ""
        parts = [np.asarray(r.audio, dtype="float32").reshape(-1) for r in model.generate(**kwargs)]
        if not parts:
            raise RuntimeError("the model returned no audio")
        audio = np.concatenate(parts)
        rate = int(model.sample_rate)
        return (audio, rate) if requested is None else (audio, rate, requested)

    return synth


def run_batch(
    lines: list[dict[str, Any]],
    out_dir: Path,
    *,
    backend: str = "real",
    load_model: LoadModel | None = None,
    emit: Emit | None = None,
) -> int:
    """Render every line; return the exit code (0 even when single lines fail)."""
    emit = emit or _print_json
    loader: LoadModel = load_model or (_mock_loader if backend == "mock" else _real_loader)
    out_dir.mkdir(parents=True, exist_ok=True)
    synths: dict[str, Synth] = {}
    for line in lines:
        line_id = str(line.get("id", ""))
        model_id = str(line.get("model", ""))
        if model_id not in synths:
            synths[model_id] = loader(model_id)  # a load failure stops the whole batch
        try:
            made = synths[model_id](line)
            samples, rate = made[0], int(made[1])
            requested = float(made[2]) if len(made) > 2 else None
            samples = resample(np.asarray(samples, dtype="float32").reshape(-1), rate)
            if samples.size == 0:
                raise RuntimeError("the model returned no audio")
            path = out_dir / f"{line_id}.wav"
            duration = write_wav(path, samples)
            event: dict[str, Any] = {"id": line_id, "path": str(path), "duration_s": duration}
            if requested is not None:
                event["duration_requested_s"] = requested
            emit(event)
        except Exception as exc:  # noqa: BLE001 - one bad line must not stop the batch
            emit({"id": line_id, "error": str(exc) or type(exc).__name__})
    return 0


def selftest(backend: str, model_id: str | None = None) -> None:
    """Render one Hindi word to a temporary WAV; raise on any failure."""
    with tempfile.TemporaryDirectory() as tmp:
        if backend != "mock" and not model_id:
            _unshadow_mlx_audio()
            importlib.import_module("mlx_audio")
            return
        events: list[dict[str, Any]] = []
        line = {
            "id": "selftest",
            "text": SELFTEST_WORD,
            "model": model_id or "selftest",
            "voice": None,
            "ref_audio": None,
            "ref_text": None,
            "speed": 1.0,
            "lang": "hi",
        }
        run_batch([line], Path(tmp), backend=backend, emit=events.append)
        if not events or "error" in events[0]:
            raise RuntimeError(events[0]["error"] if events else "no output")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tts_worker")
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--backend", choices=["real", "mock"], default="real")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)
    if args.selftest:
        try:
            selftest(args.backend, args.model)
        except Exception as exc:  # noqa: BLE001
            first = (str(exc) or type(exc).__name__).splitlines()[0]
            sys.stderr.write(f"{first}\n")
            return 1
        return 0
    if args.batch is None or args.out_dir is None:
        sys.stderr.write("--batch and --out-dir are required\n")
        return 2
    try:
        text = args.batch.read_text(encoding="utf-8")
        lines = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"cannot read batch {args.batch}: {exc}\n")
        return 2
    try:
        return run_batch(lines, args.out_dir, backend=args.backend)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"{exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
