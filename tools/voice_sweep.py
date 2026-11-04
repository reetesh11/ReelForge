"""One-lever-at-a-time sweep of the OmniVoice levers on a cloned voice (reference Mac only).

Run it inside the mlx-audio environment, for example:

    <mlx_audio_path>/.venv/bin/python tools/voice_sweep.py \
        --ref clip.wav --ref-text "text spoken in the clip" --out sweep.md

It renders one take per lever value, measures each take with `measure()` and writes a
Markdown table. This file imports nothing from `reelforge`: it runs in another environment.
"""

from __future__ import annotations

import argparse
import importlib
import re
import statistics
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

MODEL = "mlx-community/OmniVoice-bfloat16"
TEXT = "अरे आलू, इतनी देर क्यों आए हो आज? मिठाई के बिना शादी नहीं होती यार।"
ANALYSIS_RATE = 24000
PITCH_MIN_HZ = 60.0
PITCH_MAX_HZ = 400.0
FRAME_S = 0.04
HOP_S = 0.01
VOICED_MIN = 0.5
SILENT_RMS = 0.01
_LUFS_RE = re.compile(r"I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS")
COLUMNS = (
    "lever",
    "value",
    "duration (s)",
    "median pitch (Hz)",
    "pitch spread",
    "loudness (LUFS)",
    "brightness (Hz)",
)

LEVERS: list[tuple[str, list[Any]]] = [
    ("baseline", [None]),
    ("duration_s", [2.0, 3.0, 4.0, 6.0]),
    (
        "instruct",
        [
            "very low pitch",
            "low pitch",
            "moderate pitch",
            "high pitch",
            "very high pitch",
            "child",
            "teenager",
            "young adult",
            "middle-aged",
            "elderly",
            "whisper",
        ],
    ),
    ("guidance_scale", [1.0, 2.0, 3.0, 4.0]),
    ("class_temperature", [0.0, 0.3, 0.7]),
    ("position_temperature", [0.0, 2.5, 5.0, 8.0]),
    ("t_shift", [0.05, 0.1, 0.3]),
    ("num_steps", [16, 32, 48]),
    (
        "tag",
        [
            "[sigh]",
            "[laughter]",
            "[dissatisfaction-hnn]",
            "[surprise-ah]",
            "[surprise-oh]",
            "[surprise-wa]",
            "[surprise-yo]",
            "[question-en]",
            "[confirmation-en]",
        ],
    ),
]


def _decode(path: Path) -> np.ndarray[Any, Any]:
    """Mono float32 samples at `ANALYSIS_RATE`, decoded by ffmpeg."""
    res = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(ANALYSIS_RATE),
            "-f",
            "f32le",
            "-",
        ],  # fmt: skip
        capture_output=True,
        check=True,
    )
    return np.frombuffer(res.stdout, dtype="<f4").astype("float64")


def _loudness(path: Path) -> float:
    res = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ],  # fmt: skip
        capture_output=True,
        text=True,
        check=True,
    )
    found = _LUFS_RE.findall(res.stderr)
    if not found or found[-1] == "-inf":
        return float("-inf")
    return float(found[-1])


def _frame_pitch(frame: np.ndarray[Any, Any]) -> float | None:
    """Pitch of one frame from the normalised autocorrelation, or None when unvoiced."""
    frame = frame - frame.mean()
    energy = float(np.dot(frame, frame))
    if energy <= 0 or (energy / frame.size) ** 0.5 < SILENT_RMS:
        return None
    size = 1 << (2 * frame.size - 1).bit_length()
    spec = np.fft.rfft(frame, size)
    ac = np.fft.irfft(spec * np.conj(spec), size)[: frame.size] / energy
    lo = int(ANALYSIS_RATE / PITCH_MAX_HZ)
    hi = min(int(ANALYSIS_RATE / PITCH_MIN_HZ), frame.size - 2)
    if hi <= lo + 1:
        return None
    window = ac[lo : hi + 1]
    best = float(window.max())
    if best < VOICED_MIN:
        return None
    # Prefer the shortest lag whose peak is nearly as high as the best one (avoids octave errors).
    peaks = [
        i
        for i in range(1, window.size - 1)
        if window[i] >= window[i - 1] and window[i] > window[i + 1] and window[i] >= 0.9 * best
    ]
    if not peaks:
        return None
    i = peaks[0]
    a, b, c = window[i - 1], window[i], window[i + 1]
    denom = a - 2 * b + c
    shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
    return ANALYSIS_RATE / (lo + i + shift)


def _pitches(samples: np.ndarray[Any, Any]) -> list[float]:
    size, hop = round(FRAME_S * ANALYSIS_RATE), round(HOP_S * ANALYSIS_RATE)
    out: list[float] = []
    for start in range(0, max(0, samples.size - size), hop):
        f0 = _frame_pitch(samples[start : start + size])
        if f0 is not None:
            out.append(f0)
    return out


def _brightness(samples: np.ndarray[Any, Any]) -> float:
    """Spectral centroid (Hz) of the whole take."""
    if samples.size == 0:
        return 0.0
    mag = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    freqs = np.fft.rfftfreq(samples.size, 1.0 / ANALYSIS_RATE)
    total = float(mag.sum())
    return float((freqs * mag).sum() / total) if total > 0 else 0.0


def measure(path: Path) -> dict[str, float]:
    """Duration, median pitch, pitch spread (std of voiced frames), loudness and brightness."""
    samples = _decode(path)
    pitches = _pitches(samples)
    return {
        "duration_s": samples.size / ANALYSIS_RATE,
        "median_pitch_hz": float(statistics.median(pitches)) if pitches else 0.0,
        "pitch_spread": float(statistics.pstdev(pitches)) if len(pitches) > 1 else 0.0,
        "loudness_lufs": _loudness(path),
        "brightness_hz": _brightness(samples),
    }


def _unshadow() -> None:
    """Keep this folder off `sys.path` before importing the real `mlx_audio` package."""
    here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]


def _write_wav(path: Path, samples: np.ndarray[Any, Any], rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def _render(
    model: Any, text: str, extra: dict[str, Any], ref: Path, ref_text: str, dst: Path
) -> None:
    kwargs: dict[str, Any] = {
        "text": text,
        "lang_code": "hi",
        "ref_audio": str(ref),
        "ref_text": ref_text,
        **extra,
    }
    parts = [np.asarray(r.audio, dtype="float32").reshape(-1) for r in model.generate(**kwargs)]
    if not parts:
        raise RuntimeError("the model returned no audio")
    _write_wav(dst, np.concatenate(parts), int(model.sample_rate))


def _variant(lever: str, value: Any) -> tuple[str, dict[str, Any]]:
    if lever == "baseline":
        return TEXT, {}
    if lever == "tag":
        return f"{value} {TEXT}", {}
    return TEXT, {lever: value}


def _row(lever: str, value: Any, m: dict[str, float]) -> str:
    cells = [
        lever,
        "-" if value is None else str(value),
        f"{m['duration_s']:.2f}",
        f"{m['median_pitch_hz']:.1f}",
        f"{m['pitch_spread']:.1f}",
        f"{m['loudness_lufs']:.1f}",
        f"{m['brightness_hz']:.0f}",
    ]
    return "| " + " | ".join(cells) + " |"


def sweep(ref: Path, ref_text: str, model_id: str) -> str:
    _unshadow()
    utils: Any = importlib.import_module("mlx_audio.tts.utils")
    model: Any = utils.load_model(model_id)
    header = "| " + " | ".join(COLUMNS) + " |"
    rows = [header, "|" + " --- |" * len(COLUMNS)]
    with tempfile.TemporaryDirectory() as tmp:
        for lever, values in LEVERS:
            for value in values:
                text, extra = _variant(lever, value)
                dst = Path(tmp) / "take.wav"
                try:
                    _render(model, text, extra, ref, ref_text, dst)
                    rows.append(_row(lever, value, measure(dst)))
                except Exception as exc:  # noqa: BLE001 - keep sweeping; note the failure
                    rows.append(f"| {lever} | {value} | failed: {exc} | | | | |")
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice_sweep")
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)
    table = sweep(args.ref, args.ref_text, args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(table, encoding="utf-8")
    sys.stdout.write(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
