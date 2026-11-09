"""Content checks for an uploaded sound file: size, signature and an ffprobe decode check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from reelforge.audio.state import NOT_AUDIO, AudioError
from reelforge.ids import new_id
from reelforge.voice.uploads import NotAnAudioClip, probe_seconds, sniff_audio

if TYPE_CHECKING:
    from reelforge.context import AppContext


@dataclass(frozen=True)
class Clip:
    path: Path
    ext: str
    seconds: float


def too_large_text(limit_mb: int) -> str:
    return f"That clip is larger than {limit_mb} MB."


async def screen_audio(ctx: AppContext, data: bytes) -> Clip:
    """Check an uploaded file by content; the file is left in `cache/tmp` for the caller."""
    limit_mb = ctx.settings.max_upload_mb
    if len(data) > limit_mb * 1024 * 1024:
        raise AudioError(413, too_large_text(limit_mb))
    try:
        ext = sniff_audio(data)
    except NotAnAudioClip:
        raise AudioError(415, NOT_AUDIO) from None
    tmp_root = ctx.settings.cache_tmp
    tmp_root.mkdir(parents=True, exist_ok=True)
    path = tmp_root / f"{new_id()}.{ext}"
    path.write_bytes(data)
    try:
        seconds = await probe_seconds(path)
    except NotAnAudioClip:
        path.unlink(missing_ok=True)
        raise AudioError(415, NOT_AUDIO) from None
    return Clip(path, ext, seconds)
