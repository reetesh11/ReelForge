"""Join phrase WAVs with exact silences between them."""

from __future__ import annotations

import wave
from pathlib import Path

RATE = 48000


def join_wavs(paths: list[Path], gaps_s: list[float], dst: Path) -> float:
    """Write `paths` end to end into `dst`, with `gaps_s[i]` seconds of silence after file `i`.

    Inputs are 48 kHz mono 16-bit WAVs (the output of `postprocess_wav`). The silences are
    exact to the sample. Returns the duration of `dst` in seconds.
    """
    if not paths or len(gaps_s) != len(paths) - 1:
        raise ValueError("join_wavs needs one gap between each pair of files")
    frames = bytearray()
    for i, path in enumerate(paths):
        with wave.open(str(path), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, 2):
                raise ValueError(f"{path.name} is not a 48 kHz mono 16-bit WAV")
            frames += w.readframes(w.getnframes())
        if i < len(gaps_s):
            frames += b"\x00\x00" * max(0, round(gaps_s[i] * RATE))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(bytes(frames))
    return len(frames) / 2 / RATE
