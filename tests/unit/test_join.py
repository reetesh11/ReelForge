import wave

import pytest

from reelforge.voice.join import RATE, join_wavs


def _wav(path, n, rate=RATE, value=1000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(value.to_bytes(2, "little", signed=True) * n)
    return path


def _frames(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes()


def test_gap_is_exact_to_the_sample(tmp_path):
    a, b = _wav(tmp_path / "a.wav", 4800), _wav(tmp_path / "b.wav", 2400)
    dst = tmp_path / "j.wav"
    seconds = join_wavs([a, b], [0.15], dst)
    assert _frames(dst) == 4800 + 7200 + 2400
    assert seconds == pytest.approx(14400 / RATE)


def test_three_files_and_zero_gap(tmp_path):
    files = [_wav(tmp_path / f"{i}.wav", 100) for i in range(3)]
    dst = tmp_path / "j.wav"
    join_wavs(files, [0.0, 0.01], dst)
    assert _frames(dst) == 300 + 480


def test_single_file_is_copied(tmp_path):
    a = _wav(tmp_path / "a.wav", 123)
    assert join_wavs([a], [], tmp_path / "o.wav") == pytest.approx(123 / RATE)


def test_wrong_gap_count_or_format_is_an_error(tmp_path):
    a = _wav(tmp_path / "a.wav", 10)
    with pytest.raises(ValueError):
        join_wavs([a, a], [], tmp_path / "o.wav")
    odd = _wav(tmp_path / "odd.wav", 10, rate=24000)
    with pytest.raises(ValueError, match="48 kHz"):
        join_wavs([odd], [], tmp_path / "o.wav")
