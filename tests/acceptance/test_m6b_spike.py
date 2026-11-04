"""m6b AC-13 (measurement tool): `tools/voice_sweep.py` exposes `measure`. Table results are manual."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from m6b_helpers import wav_bytes

ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = ROOT / "tools" / "voice_sweep.py"
    assert path.exists(), "tools/voice_sweep.py is missing"
    spec = importlib.util.spec_from_file_location("voice_sweep_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_measure_reports_the_five_values_for_a_known_tone(tmp_path):
    mod = _load()
    p = tmp_path / "tone.wav"
    p.write_bytes(wav_bytes(2.0, rate=24000, freq=220.0, amp=0.5))
    m = mod.measure(p)
    assert set(m) == {"duration_s", "median_pitch_hz", "pitch_spread", "loudness_lufs", "brightness_hz"}
    assert m["duration_s"] == pytest.approx(2.0, abs=0.05)
    assert m["median_pitch_hz"] == pytest.approx(220.0, rel=0.05)
    assert m["pitch_spread"] >= 0 and m["pitch_spread"] < 20
    assert -40 < m["loudness_lufs"] < -5
    assert m["brightness_hz"] == pytest.approx(220.0, rel=0.25)


def test_measure_orders_two_tones_by_pitch_and_brightness(tmp_path):
    mod = _load()
    lo, hi = tmp_path / "lo.wav", tmp_path / "hi.wav"
    lo.write_bytes(wav_bytes(1.5, rate=24000, freq=150.0, amp=0.4))
    hi.write_bytes(wav_bytes(1.5, rate=24000, freq=300.0, amp=0.4))
    a, b = mod.measure(lo), mod.measure(hi)
    assert b["median_pitch_hz"] > a["median_pitch_hz"] * 1.6
    assert b["brightness_hz"] > a["brightness_hz"]


def test_the_tool_imports_no_reelforge_module():
    src = (ROOT / "tools" / "voice_sweep.py").read_text()
    assert "import reelforge" not in src and "from reelforge" not in src
