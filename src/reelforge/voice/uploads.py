"""Content checks for uploaded voice clips: signature sniffing plus an `ffprobe` decode check."""

from __future__ import annotations

import json
from pathlib import Path

from reelforge.adapters.runner import run_command

PROBE_TIMEOUT_S = 30.0
_MP3_SYNC = (0xFB, 0xF3, 0xF2, 0xE3, 0xE2, 0xFA)


class NotAnAudioClip(ValueError):
    pass


def sniff_audio(data: bytes) -> str:
    """Return the extension judged by content (WAV, MP3, M4A, FLAC, OGG); raise NotAnAudioClip."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"OggS":
        return "ogg"
    if data[4:8] == b"ftyp":
        return "m4a"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] in _MP3_SYNC):
        return "mp3"
    raise NotAnAudioClip("not a WAV, MP3, M4A, FLAC or OGG clip")


async def probe_seconds(path: Path) -> float:
    """Decode-check the file with ffprobe and return its length; raise NotAnAudioClip."""
    res = await run_command(
        [
            "ffprobe", "-v", "error", "-of", "json",
            "-show_entries", "format=duration:stream=codec_type",
            str(path),
        ],
        timeout_s=PROBE_TIMEOUT_S,
    )  # fmt: skip
    if res.exit_code != 0:
        raise NotAnAudioClip(res.stderr.strip() or "ffprobe failed")
    try:
        info = json.loads(res.stdout)
        has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        seconds = float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise NotAnAudioClip("no readable audio") from None
    if not has_audio or not seconds > 0:
        raise NotAnAudioClip("no readable audio")
    return seconds
