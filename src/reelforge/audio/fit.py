"""Make an audio file exactly as long as its cue: loop with a crossfade, or trim."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from reelforge.adapters.runner import run_command
from reelforge.assembly import ffmpeg

SAMPLE_RATE = 48000
FIT_TIMEOUT_S = 300.0
MAX_COPIES = 400
MIN_SECONDS = 0.01


class FitError(ValueError):
    """The source could not be fitted (unreadable, empty or ffmpeg failed)."""


def _copies(source_s: float, seconds: float, crossfade_s: float) -> int:
    """Copies of the source that cover `seconds` when each join overlaps by `crossfade_s`."""
    step = source_s - crossfade_s
    return max(2, math.ceil((seconds - source_s) / step) + 1)


def _graph(source_s: float, seconds: float, crossfade_s: float, channels: int) -> str:
    layout = "mono" if channels == 1 else "stereo"
    fmt = f"aresample={SAMPLE_RATE},aformat=sample_fmts=s16:channel_layouts={layout}"
    tail = f"atrim=duration={seconds:.6f},asetpts=PTS-STARTPTS,apad=whole_dur={seconds:.6f}"
    if source_s >= seconds - 1e-6:
        return f"[0:a]{fmt},{tail}[out]"
    xf = min(crossfade_s, source_s / 2)
    if xf <= 0.001:
        n = max(2, math.ceil(seconds / source_s))
        return f"[0:a]{fmt},aloop=loop={n}:size={int(source_s * SAMPLE_RATE) + 1},{tail}[out]"
    n = _copies(source_s, seconds, xf)
    if n > MAX_COPIES:
        raise FitError("The clip is too short to fill this cue.")
    labels = "".join(f"[c{i}]" for i in range(n))
    parts = [f"[0:a]{fmt},asplit={n}{labels}"]
    prev = "c0"
    for i in range(1, n):
        out = "x" if i == n - 1 else f"j{i}"
        parts.append(f"[{prev}][c{i}]acrossfade=d={xf:.6f}:c1=qsin:c2=qsin[{out}]")
        prev = out
    parts.append(f"[{prev}]{tail}[out]")
    return ";".join(parts)


async def fit_to_length(
    src: Path, dst: Path, seconds: float, *, crossfade_s: float = 1.0, channels: int = 2
) -> None:
    """Write `dst` as 48 kHz 16-bit WAV (stereo, or mono for stored takes) of exactly `seconds`."""
    if not seconds >= MIN_SECONDS:
        raise FitError("The cue has no length.")
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise FitError(ffmpeg.NO_FFMPEG)
    try:
        source_s = ffmpeg.media_duration(src, "audio")
    except (ValueError, OSError):
        raise FitError("That file is not an audio clip.") from None
    graph = _graph(source_s, seconds, max(0.0, crossfade_s), channels)
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(f".{dst.name}.part")
    argv = [
        exe, "-y", "-nostdin", "-hide_banner", "-nostats", "-loglevel", "error",
        "-i", str(src), "-filter_complex", graph, "-map", "[out]",
        "-ar", str(SAMPLE_RATE), "-ac", str(channels), "-c:a", "pcm_s16le", "-f", "wav", str(part),
    ]  # fmt: skip
    res = await run_command(argv, timeout_s=FIT_TIMEOUT_S)
    if res.exit_code != 0:
        part.unlink(missing_ok=True)
        raise FitError(
            res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "ffmpeg failed"
        )
    part.replace(dst)
