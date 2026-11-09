import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m4_helpers import read_wav, wav_bytes  # noqa: E402  # pyright: ignore[reportMissingImports]
from rf_helpers import run_async  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.audio.fit import FitError, fit_to_length  # noqa: E402


def _fit(tmp_path, seconds_in, seconds_out, **kw):
    src, dst = tmp_path / "s.wav", tmp_path / "d.wav"
    src.write_bytes(wav_bytes(seconds_in, rate=24000))
    run_async(fit_to_length(src, dst, seconds_out, **kw))
    samples, rate, channels, _ = read_wav(dst)
    return len(samples) / rate / channels


@pytest.mark.parametrize(("have", "want"), [(0.7, 2.0), (3.0, 8.0), (5.0, 2.0), (2.0, 2.0)])
def test_exact_length(tmp_path, have, want):
    assert _fit(tmp_path, have, want) == pytest.approx(want, abs=0.001)


def test_a_source_shorter_than_the_crossfade_still_fills_the_cue(tmp_path):
    assert _fit(tmp_path, 0.4, 3.0, crossfade_s=1.0) == pytest.approx(3.0, abs=0.001)


def test_an_unreadable_source_is_refused(tmp_path):
    src = tmp_path / "s.wav"
    src.write_bytes(b"nope")
    with pytest.raises(FitError):
        run_async(fit_to_length(src, tmp_path / "d.wav", 1.0))
