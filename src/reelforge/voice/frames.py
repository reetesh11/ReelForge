"""Frame math: a shot is `8k + 1` frames at 24 fps, with at least one block (9 frames)."""

from __future__ import annotations

import math

FPS = 24
MIN_FRAMES = 9


def frames_for(duration_s: float) -> int:
    """Smallest `8k + 1` frame count (k >= 1) whose length covers `duration_s`."""
    if not duration_s > 0:
        raise ValueError("duration must be greater than 0")
    frames = 8 * math.ceil((duration_s * FPS - 1) / 8) + 1
    return max(MIN_FRAMES, frames)


def shot_length_s(frames: int) -> float:
    return frames / FPS
