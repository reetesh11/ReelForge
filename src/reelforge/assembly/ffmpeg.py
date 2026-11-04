"""ffmpeg and ffprobe wrappers (argument lists only, never a shell)."""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.adapters.runner import CommandResult, run_command
from reelforge.assembly.state import StepError

if TYPE_CHECKING:
    from reelforge.context import AppContext

NO_FFMPEG = "ffmpeg is not available or lacks the subtitles filter. Run Settings & status to check."
PROBE_TIMEOUT_S = 60.0


@functools.lru_cache(maxsize=1)
def _filters_text() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        return ""
    try:
        res = subprocess.run(  # noqa: S603
            [exe, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout


@functools.lru_cache(maxsize=1)
def _has_filter_complex_script() -> bool:
    exe = shutil.which("ffmpeg")
    if exe is None:
        return False
    try:
        res = subprocess.run(  # noqa: S603
            [exe, "-hide_banner", "-h", "full"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "filter_complex_script" in res.stdout


def filter_script_args(script: Path) -> list[str]:
    """The ffmpeg options that read a filter graph from `script` (the name changed in ffmpeg 7)."""
    if _has_filter_complex_script():
        return ["-filter_complex_script", str(script)]
    return ["-/filter_complex", str(script)]


def has_filter(name: str) -> bool:
    """True when `ffmpeg -filters` lists the filter (the list is read once)."""
    for line in _filters_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return True
    return False


def probe(path: Path) -> dict[str, Any]:
    """`ffprobe` JSON (streams and format) for a media file; raises ValueError when unreadable."""
    exe = shutil.which("ffprobe")
    if exe is None:
        raise ValueError("ffprobe not found")
    res = subprocess.run(  # noqa: S603
        [exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S,
        check=False,
    )
    if res.returncode != 0:
        raise ValueError("ffprobe could not read the file")
    try:
        data: dict[str, Any] = json.loads(res.stdout)
    except ValueError:
        raise ValueError("ffprobe returned no data") from None
    return data


def stream(info: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            return dict(s)
    return None


def media_duration(path: Path, kind: str = "video") -> float:
    """Length in seconds of the first stream of `kind` (the container length as a fallback)."""
    info = probe(path)
    s = stream(info, kind)
    for source in (s or {}, info.get("format", {})):
        try:
            value = float(source.get("duration") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    raise ValueError("no duration")


def ffmpeg_exe(step: str) -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise StepError(step, NO_FFMPEG)
    return exe


async def run_ffmpeg(
    ctx: AppContext,
    argv_tail: Sequence[str],
    cancel: CancelToken,
    *,
    step: str,
    on_stdout_line: Callable[[str], None] | None = None,
) -> CommandResult:
    """Run ffmpeg with `argv_tail`; a non-zero exit raises StepError with the last error line."""
    argv = [ffmpeg_exe(step), "-y", "-nostdin", "-hide_banner", "-nostats", *argv_tail]
    result = await run_command(
        argv,
        timeout_s=ctx.settings.command_timeout_s,
        cancel=cancel,
        sample_interval_s=ctx.settings.sample_interval_s,
        on_stdout_line=on_stdout_line,
    )
    if result.cancelled or cancel.cancelled:
        raise AdapterError("cancelled")
    if result.exit_code != 0:
        lines = [ln.strip() for ln in result.stderr.splitlines() if ln.strip()]
        reason = lines[-1] if lines else (result.error or "ffmpeg failed")
        raise StepError(step, f"ffmpeg failed: {reason}")
    return result
