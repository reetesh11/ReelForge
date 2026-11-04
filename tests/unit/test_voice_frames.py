import random

import pytest

from reelforge.voice.frames import FPS, MIN_FRAMES, frames_for, shot_length_s


def test_known_values():
    assert frames_for(2.9) == 73
    assert frames_for(3.32) == 81
    assert frames_for(0.001) == MIN_FRAMES


def test_property_8k_plus_1_and_covers_duration():
    rng = random.Random(9)
    for _ in range(3000):
        d = rng.uniform(0.01, 40)
        f = frames_for(d)
        assert f >= 9 and (f - 1) % 8 == 0
        assert shot_length_s(f) >= d - 1e-9
        assert f == 9 or shot_length_s(f - 8) < d


@pytest.mark.parametrize("bad", [0, -0.5, float("nan")])
def test_rejects_non_positive(bad):
    with pytest.raises(ValueError):
        frames_for(bad)


def test_fps():
    assert FPS == 24 and shot_length_s(73) == pytest.approx(73 / 24)
