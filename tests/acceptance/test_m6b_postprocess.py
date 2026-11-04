"""m6b AC-5: pitch, tempo and gain through ffmpeg, and a clear failure without `rubberband`."""

from __future__ import annotations

import pytest
from m6b_helpers import read_wav, rms, tone_freq, wav_bytes
from rf_helpers import run_async

from reelforge.adapters.base import AdapterError

NO_RUBBERBAND = 'ffmpeg is missing the "rubberband" filter, needed for pitch and tempo changes. Install ffmpeg-full.'


def _src(tmp_path, seconds=2.0, freq=300.0):
    p = tmp_path / "tone.wav"
    p.write_bytes(wav_bytes(seconds, rate=24000, freq=freq, amp=0.5))
    return p


def _run(tmp_path, name, **kw):
    from reelforge.adapters.mlx_audio import postprocess_wav

    dst = tmp_path / f"{name}.wav"
    secs = run_async(postprocess_wav(_src(tmp_path), dst, **kw))
    s, rate, _, _ = read_wav(dst)
    return dst, secs, s, rate


def test_positive_semitones_raise_and_negative_lower_the_pitch(tmp_path):
    _, _, base_s, rate = _run(tmp_path, "base")
    _, _, up, _ = _run(tmp_path, "up", semitones=4.0)
    _, _, down, _ = _run(tmp_path, "down", semitones=-4.0)
    f0, f_up, f_down = tone_freq(base_s, rate), tone_freq(up, rate), tone_freq(down, rate)
    assert f_up > f0 * 1.15 and f_down < f0 * 0.85
    assert f_up == pytest.approx(f0 * 2 ** (4 / 12), rel=0.06)
    assert f_down == pytest.approx(f0 * 2 ** (-4 / 12), rel=0.06)


def test_tempo_changes_length_and_returns_duration(tmp_path):
    _, d_base, base_s, rate = _run(tmp_path, "base")
    _, d_fast, fast, _ = _run(tmp_path, "fast", tempo=2.0)
    assert d_fast == pytest.approx(len(fast) / rate, abs=0.05)
    assert d_fast == pytest.approx(d_base / 2, rel=0.15)
    assert tone_freq(fast, rate) == pytest.approx(tone_freq(base_s, rate), rel=0.05)


def test_gain_db_lowers_loudness_after_normalisation(tmp_path):
    _, _, base_s, _ = _run(tmp_path, "base")
    _, _, quiet, _ = _run(tmp_path, "quiet", gain_db=-6.0)
    assert rms(quiet) / rms(base_s) == pytest.approx(0.5, rel=0.1)


def test_missing_rubberband_fails_with_message_and_skips_nothing(tmp_path, monkeypatch):
    from reelforge.adapters import mlx_audio
    from reelforge.adapters.mlx_audio import postprocess_wav

    monkeypatch.setattr(mlx_audio, "ffmpeg_has_filter", lambda name: False)
    for kw in ({"semitones": 3.0}, {"tempo": 1.2}):
        dst = tmp_path / "out.wav"
        with pytest.raises(AdapterError) as ei:
            run_async(postprocess_wav(_src(tmp_path), dst, **kw))
        assert str(ei.value) == NO_RUBBERBAND
        assert not dst.exists()
    # no pitch or tempo change asked for: the filter is not needed
    dst = tmp_path / "plain.wav"
    assert run_async(postprocess_wav(_src(tmp_path), dst, gain_db=-1.0)) > 0 and dst.exists()


def test_ffmpeg_has_filter_reports_real_filters():
    from reelforge.adapters.mlx_audio import ffmpeg_has_filter

    assert ffmpeg_has_filter("volume") is True
    assert ffmpeg_has_filter("no_such_filter_xyz") is False


def test_ffmpeg_runs_as_argument_lists_with_rubberband_args(tmp_path, monkeypatch):
    import re

    from reelforge.adapters import mlx_audio

    seen: list = []
    real = mlx_audio.run_command

    async def spy(argv, *a, **kw):
        seen.append(argv)
        return await real(argv, *a, **kw)

    monkeypatch.setattr(mlx_audio, "run_command", spy)
    _run(tmp_path, "up", semitones=4.0, tempo=1.1, gain_db=-2.0)
    assert seen and all(isinstance(a, list) and all(isinstance(x, str) for x in a) for a in seen)
    graphs = [a[a.index("-af") + 1] for a in seen if "-af" in a]
    m = re.search(r"rubberband=pitch=([0-9.]+):tempo=([0-9.]+)", " ".join(graphs))
    assert m, graphs
    assert float(m.group(1)) == pytest.approx(2 ** (4 / 12), rel=1e-3)
    assert float(m.group(2)) == pytest.approx(1.1, rel=1e-3)
