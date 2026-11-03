"""m4 AC-3 (frame math) and the speed/pause rules of AC-9. Pure functions."""

from __future__ import annotations

import math
import random

import pytest


def test_frames_known_values():
    from reelforge.voice.frames import frames_for

    assert frames_for(2.9) == 73
    assert frames_for(3.32) == 81


def test_frames_property_8k_plus_1():
    from reelforge.voice.frames import frames_for

    rng = random.Random(4)
    durations = [rng.uniform(0.01, 30.0) for _ in range(2000)] + [0.001, 0.375, 0.4, 1.0, 2.0, 5.0]
    for d in durations:
        f = frames_for(d)
        assert f >= 9 and (f - 1) % 8 == 0, (d, f)
        assert f == max(9, 8 * math.ceil((d * 24 - 1) / 8) + 1), (d, f)
        # the shot is long enough for the line
        assert f / 24 >= d - 1e-9, (d, f)


@pytest.mark.parametrize("bad", [0, 0.0, -1.0])
def test_frames_rejects_non_positive(bad):
    from reelforge.voice.frames import frames_for

    with pytest.raises(ValueError):
        frames_for(bad)


def test_fps_and_shot_length():
    from reelforge.voice.frames import FPS, shot_length_s

    assert FPS == 24
    assert shot_length_s(73) == pytest.approx(73 / 24)


def test_speed_and_pause_constants_and_bounds():
    from reelforge.adapters import mlx_audio as m

    assert (m.SPEED_MIN, m.SPEED_MAX, m.PAUSE_MIN, m.PAUSE_MAX) == (0.8, 1.25, 0.0, 1.0)
    assert m.check_speed(0.8) == 0.8 and m.check_speed(1.25) == 1.25 and m.check_speed(1.0) == 1.0
    for bad in (0.79, 1.26, 0.0, -1.0, 2.0):
        with pytest.raises(ValueError, match="speed must be between 0.8 and 1.25"):
            m.check_speed(bad)
    assert m.check_pause("pause_before", 0) == 0 and m.check_pause("pause_after", 1) == 1
    for bad in (-0.1, 1.01, 5):
        with pytest.raises(ValueError, match="pause_after must be between 0 and 1 seconds"):
            m.check_pause("pause_after", bad)


def test_plan_speed_native_vs_atempo():
    from reelforge.adapters.mlx_audio import plan_speed

    assert plan_speed("kokoro", 1.1) == (1.1, None)
    assert plan_speed("omnivoice", 1.1) == (1.0, 1.1)
    with pytest.raises(ValueError):
        plan_speed("kokoro", 1.5)
    with pytest.raises(ValueError):
        plan_speed("omnivoice", 0.5)
