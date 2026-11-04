import importlib.util
import wave
from pathlib import Path

import numpy as np

TOOL = Path(__file__).resolve().parents[2] / "tools" / "voice_sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("voice_sweep_unit", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, samples: np.ndarray, rate: int = 24000) -> None:
    pcm = (samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def test_silence_has_no_pitch(tmp_path):
    p = tmp_path / "s.wav"
    _write(p, np.zeros(24000))
    m = _load().measure(p)
    assert m["median_pitch_hz"] == 0.0 and m["pitch_spread"] == 0.0
    assert abs(m["duration_s"] - 1.0) < 0.01


def test_rising_pitch_has_spread(tmp_path):
    t = np.arange(48000) / 24000
    phase = 2 * np.pi * (150 * t + 50 * t**2)  # 150 Hz sliding to 350 Hz
    p = tmp_path / "glide.wav"
    _write(p, 0.4 * np.sin(phase))
    m = _load().measure(p)
    assert 180 < m["median_pitch_hz"] < 320 and m["pitch_spread"] > 20


def test_table_row_has_seven_cells():
    mod = _load()
    row = mod._row(
        "tag",
        "[sigh]",
        {
            "duration_s": 1.0,
            "median_pitch_hz": 100.0,
            "pitch_spread": 3.0,
            "loudness_lufs": -20.0,
            "brightness_hz": 500.0,
        },
    )
    assert row.count("|") == len(mod.COLUMNS) + 1
