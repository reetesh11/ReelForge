import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m4_helpers import wav_bytes  # noqa: E402  # pyright: ignore[reportMissingImports]
from rf_helpers import make_ctx, make_settings, run_async  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.audio.state import NOT_AUDIO, AudioError  # noqa: E402
from reelforge.audio.uploads import screen_audio  # noqa: E402


def _ctx(tmp_path, **over):
    return make_ctx(make_settings(tmp_path, **over))


@pytest.mark.parametrize("data", [b"", b"%PDF-1.4", b"RIFF\x00\x00\x00\x00WAVEjunk"])
def test_not_audio_is_415(tmp_path, data):
    with pytest.raises(AudioError) as ei:
        run_async(screen_audio(_ctx(tmp_path), data))
    assert (ei.value.status, ei.value.message) == (415, NOT_AUDIO)
    assert list((tmp_path / "data" / "cache" / "tmp").iterdir()) == []


def test_over_the_limit_is_413(tmp_path):
    with pytest.raises(AudioError) as ei:
        run_async(screen_audio(_ctx(tmp_path, max_upload_mb=1), wav_bytes(25.0, rate=24000)))
    assert (ei.value.status, ei.value.message) == (413, "That clip is larger than 1 MB.")


def test_a_real_wav_passes(tmp_path):
    clip = run_async(screen_audio(_ctx(tmp_path), wav_bytes(1.0, rate=24000)))
    assert clip.ext == "wav" and clip.seconds == pytest.approx(1.0, abs=0.05)
