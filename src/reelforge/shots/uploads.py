"""Checks on an uploaded clip: size, then ffprobe for a vertical 9:16 video of up to 20 s."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from reelforge.ids import new_id
from reelforge.shots.media import NotAVideo, VideoInfo, probe_video
from reelforge.shots.state import ShotError

if TYPE_CHECKING:
    from reelforge.context import AppContext

NOT_VIDEO = "That file is not a video."
NOT_VERTICAL = "The clip must be vertical 9:16."
TOO_LONG = "The clip must be 20 seconds or shorter."
MAX_CLIP_S = 20.0
RATIO_TOLERANCE = 0.01


@dataclass(frozen=True)
class Clip:
    path: Path
    ext: str
    info: VideoInfo


async def screen_clip(ctx: AppContext, data: bytes) -> Clip:
    """Check an uploaded clip by content; the file is left in `cache/tmp` for the store."""
    limit_mb = ctx.settings.max_clip_mb
    if len(data) > limit_mb * 1024 * 1024:
        raise ShotError(413, f"That clip is larger than {limit_mb} MB.")
    if not data:
        raise ShotError(415, NOT_VIDEO)
    tmp_root = ctx.settings.cache_tmp
    tmp_root.mkdir(parents=True, exist_ok=True)
    path = tmp_root / f"{new_id()}.clip"
    path.write_bytes(data)
    try:
        try:
            info = await probe_video(path)
        except NotAVideo:
            raise ShotError(415, NOT_VIDEO) from None
        if info.height <= 0 or abs(info.width / info.height - 9 / 16) > (9 / 16) * RATIO_TOLERANCE:
            raise ShotError(422, NOT_VERTICAL)
        if info.duration_s > MAX_CLIP_S:
            raise ShotError(422, TOO_LONG)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    ext = "webm" if "webm" in info.format_name else "mp4"
    final = path.with_suffix(f".{ext}")
    path.rename(final)
    return Clip(final, ext, info)
