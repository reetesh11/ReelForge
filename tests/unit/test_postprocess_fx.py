import asyncio
import math
import struct
import wave

import pytest

from reelforge.adapters import mlx_audio
from reelforge.adapters.base import AdapterError
from reelforge.adapters.mlx_audio import NO_RUBBERBAND, ffmpeg_has_filter, postprocess_wav

needs_rubberband = pytest.mark.skipif(
    not ffmpeg_has_filter("rubberband"), reason="this ffmpeg has no rubberband filter"
)


def _tone(path, seconds=1.0, freq=300.0, rate=24000):
    n = int(seconds * rate)
    frames = b"".join(
        struct.pack("<h", int(16000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return path


def _freq(path):
    with wave.open(str(path), "rb") as w:
        rate, raw = w.getframerate(), w.readframes(w.getnframes())
    s = struct.unpack(f"<{len(raw) // 2}h", raw)
    mid = s[len(s) // 5 : -len(s) // 5]
    cross = sum(1 for a, b in zip(mid, mid[1:], strict=False) if (a < 0) != (b < 0))
    return cross / 2 / (len(mid) / rate)


@needs_rubberband
def test_octave_up_doubles_the_frequency(tmp_path):
    src, dst = _tone(tmp_path / "s.wav"), tmp_path / "d.wav"
    asyncio.run(postprocess_wav(src, dst, semitones=12.0))
    assert _freq(dst) == pytest.approx(600.0, rel=0.06)


@needs_rubberband
def test_tempo_alone_keeps_pitch(tmp_path):
    src, dst = _tone(tmp_path / "s.wav", seconds=2.0), tmp_path / "d.wav"
    secs = asyncio.run(postprocess_wav(src, dst, tempo=1.25))
    assert secs == pytest.approx(1.6, rel=0.15) and _freq(dst) == pytest.approx(300.0, rel=0.05)


def test_pitch_and_tempo_need_rubberband_but_gain_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(mlx_audio, "ffmpeg_has_filter", lambda name: False)
    src = _tone(tmp_path / "s.wav")
    with pytest.raises(AdapterError) as ei:
        asyncio.run(postprocess_wav(src, tmp_path / "d.wav", semitones=-1.0))
    assert str(ei.value) == NO_RUBBERBAND and not (tmp_path / "d.wav").exists()
    assert asyncio.run(postprocess_wav(src, tmp_path / "g.wav", gain_db=3.0)) > 0


def test_no_effect_requested_never_asks_for_the_filter(tmp_path, monkeypatch):
    def boom(name):
        raise AssertionError("filter list was read")

    monkeypatch.setattr(mlx_audio, "ffmpeg_has_filter", boom)
    asyncio.run(postprocess_wav(_tone(tmp_path / "s.wav"), tmp_path / "d.wav"))


def test_unknown_filter_is_not_reported():
    assert ffmpeg_has_filter("definitely_not_a_filter") is False
