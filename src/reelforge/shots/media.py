"""ffprobe and ffmpeg helpers for clips: probing and cutting the last frame."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from reelforge.adapters.runner import run_command

PROBE_TIMEOUT_S = 60.0


class NotAVideo(ValueError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration_s: float
    format_name: str


async def probe_video(path: Path) -> VideoInfo:
    """Width, height and length of the first video stream; raise NotAVideo otherwise."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise NotAVideo("ffprobe not found")
    res = await run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height:format=duration,format_name",
            "-of",
            "json",
            str(path),
        ],
        timeout_s=PROBE_TIMEOUT_S,
    )
    if res.exit_code != 0:
        raise NotAVideo("ffprobe could not read the file")
    try:
        data = json.loads(res.stdout)
        streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        stream = streams[0]
        fmt = data.get("format", {})
        width, height = int(stream["width"]), int(stream["height"])
        duration = float(fmt.get("duration") or 0.0)
        return VideoInfo(width, height, duration, str(fmt.get("format_name", "")))
    except (ValueError, KeyError, IndexError, TypeError):
        raise NotAVideo("no video stream") from None


async def extract_last_frame(video: Path, out_png: Path) -> None:
    """Write the final frame of `video` as a PNG."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise NotAVideo("ffmpeg not found")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    res = await run_command(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-sseof",
            "-0.5",
            "-i",
            str(video),
            "-an",
            "-update",
            "1",
            str(out_png),
        ],
        timeout_s=PROBE_TIMEOUT_S,
    )
    if res.exit_code != 0 or not out_png.is_file():
        raise NotAVideo("could not read the last frame")
