"""ltx-2-mlx adapter: flag check for doctor, and `run()` for a2v / generate shots."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path

from reelforge.adapters.base import (
    AdapterError,
    CancelToken,
    HealthReport,
    ProducedFile,
    ProgressCb,
    TaskSpec,
)
from reelforge.adapters.runner import run_command
from reelforge.jobs.classify import classify_exit

EXE_NAME = "ltx-2-mlx"
OOM_MESSAGE = "Killed, likely out of memory."
HELP_TIMEOUT_S = 30.0

REQUIRED_FLAGS: dict[str, tuple[str, ...]] = {
    "a2v": (
        "--prompt",
        "--output",
        "--audio",
        "--image",
        "--frame-rate",
        "--frames",
        "--width",
        "--height",
        "--model",
        "--seed",
        "--distilled",
        "--low-ram",
    ),
    "generate": (
        "--prompt",
        "--output",
        "--image",
        "--frame-rate",
        "--frames",
        "--width",
        "--height",
        "--model",
        "--seed",
        "--distilled",
        "--low-ram",
        "--no-audio",
    ),
    "extend": (
        "--prompt",
        "--output",
        "--video",
        "--extend-frames",
        "--distilled",
        "--low-ram",
        "--image",
    ),
}

_FLAG_RE = re.compile(r"--[a-z0-9][a-z0-9-]*")

# (exe path, mtime_ns, size) -> subcommand -> flags (None when `--help` could not run)
_HELP_CACHE: dict[tuple[str, int, int], dict[str, set[str] | None]] = {}


def parse_flags(help_text: str) -> set[str]:
    """Every `--long-option` token in a `--help` text."""
    return set(_FLAG_RE.findall(help_text))


def _run_help(exe: Path, sub: str) -> set[str] | None:
    try:
        res = subprocess.run(  # noqa: S603
            [str(exe), sub, "--help"],
            capture_output=True,
            text=True,
            timeout=HELP_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return parse_flags(res.stdout + "\n" + res.stderr)


def _help_flags(exe: Path) -> dict[str, set[str] | None]:
    st = exe.stat()
    key = (str(exe), st.st_mtime_ns, st.st_size)
    cached = _HELP_CACHE.get(key)
    if cached is None:
        cached = {sub: _run_help(exe, sub) for sub in REQUIRED_FLAGS}
        _HELP_CACHE[key] = cached
    return cached


AUDIO_PAD_MARGIN_S = 0.25


def _pad_audio(src: Path, dst: Path, clip_s: float) -> Path:
    """Pad a voice take with silence so LTX a2v has enough audio latent frames.

    A line shorter than the clip makes ltx-2-mlx refuse it. apad only adds
    silence when the take is shorter, so longer takes pass through unchanged.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return src
    whole = f"{clip_s + AUDIO_PAD_MARGIN_S:.3f}"
    proc = subprocess.run(  # noqa: S603
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-af", f"apad=whole_dur={whole}", str(dst)],
        capture_output=True,
        check=False,
    )
    return dst if proc.returncode == 0 and dst.is_file() else src


class LtxAdapter:
    name = "ltx"
    version = "ltx-2-mlx"

    def __init__(
        self,
        project_path: Path | None,
        *,
        timeout_s: float = 1800.0,
        sample_interval_s: float = 2.0,
    ) -> None:
        self.project_path = project_path
        self.timeout_s = timeout_s
        self.sample_interval_s = sample_interval_s

    @property
    def executable(self) -> Path | None:
        if self.project_path is None:
            return None
        return self.project_path / ".venv" / "bin" / EXE_NAME

    def _fail(self, detail: str) -> HealthReport:
        return HealthReport(name=self.name, ok=False, detail=detail)

    def check(self) -> HealthReport:
        if self.project_path is None:
            return self._fail("ltx-2-mlx path is not configured")
        if not self.project_path.is_dir():
            return self._fail(f"ltx-2-mlx project not found at {self.project_path}")
        if not (self.project_path / ".venv").is_dir():
            return self._fail(f"ltx-2-mlx has no virtual environment in {self.project_path}")
        exe = self.executable
        if exe is None or not exe.is_file():
            return self._fail(
                f"ltx-2-mlx executable not found in {self.project_path / '.venv' / 'bin'}"
            )
        found = _help_flags(exe)
        for sub in REQUIRED_FLAGS:
            if found.get(sub) is None:
                return self._fail(f"ltx-2-mlx could not run '{sub} --help'")
        missing: list[str] = []
        for sub, required in REQUIRED_FLAGS.items():
            have = found[sub] or set()
            lacks = [f for f in required if f not in have]
            if lacks:
                missing.append(f"{sub}: {', '.join(lacks)}")
        if missing:
            return self._fail(f"ltx-2-mlx is missing required options: {'; '.join(missing)}")
        return HealthReport(
            name=self.name,
            ok=True,
            detail=f"ltx-2-mlx at {self.project_path}",
            version=self.version,
        )

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)

    async def capabilities(self) -> set[str]:
        return {"video"}

    def _lists_steps(self, exe: Path, sub: str) -> bool:
        try:
            flags = _help_flags(exe).get(sub)
        except OSError:
            return False
        return bool(flags) and "--steps" in (flags or set())

    async def run(
        self,
        task: TaskSpec,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        ctx_job_id: str | None = None,
    ) -> list[ProducedFile]:
        exe = self.executable
        if exe is None or not exe.is_file():
            raise AdapterError("ltx-2-mlx executable not found")
        mode = str(task.params.get("mode", "generate"))
        if mode not in ("a2v", "generate"):
            raise AdapterError(f"unknown ltx-2-mlx mode {mode!r}")
        if not task.input_paths or (mode == "a2v" and len(task.input_paths) < 2):
            raise AdapterError("ltx-2-mlx needs a key frame (and a voice take for a2v)")
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "out.mp4"
        width = int(task.params["width"])
        height = int(task.params["height"])
        fps = int(task.params["fps"])
        frames = int(task.params["frames"])
        argv = [
            str(exe),
            mode,
            "--prompt",
            task.prompt,
            "--output",
            str(out),
            "--image",
            str(task.input_paths[0]),
        ]
        if mode == "a2v":
            audio = await asyncio.to_thread(
                _pad_audio, task.input_paths[1], out_dir / "audio_padded.wav", frames / max(fps, 1)
            )
            argv += ["--audio", str(audio)]
        else:
            argv.append("--no-audio")
        argv += [
            "--frame-rate",
            str(fps),
            "--frames",
            str(frames),
            "--width",
            str(width),
            "--height",
            str(height),
            "--model",
            task.model.id,
            "--seed",
            str(task.seed),
            "--distilled",
            "--low-ram",
        ]
        if task.model.steps is not None and self._lists_steps(exe, mode):
            argv += ["--steps", str(task.model.steps)]
        progress(1, "starting")
        res = await run_command(
            argv,
            timeout_s=self.timeout_s,
            cancel=cancel,
            sample_interval_s=self.sample_interval_s,
            job_id=ctx_job_id,
        )
        if res.cancelled:
            raise AdapterError("cancelled")
        if res.timed_out:
            raise AdapterError("Timed out")
        if classify_exit(res.exit_code) is not None:
            raise AdapterError(OOM_MESSAGE)
        if res.exit_code != 0:
            lines = [ln.strip() for ln in res.stderr.splitlines() if ln.strip()]
            detail = lines[-1] if lines else (res.error or f"exit code {res.exit_code}")
            raise AdapterError(f"ltx-2-mlx failed: {detail}")
        if not out.is_file():
            raise AdapterError("ltx-2-mlx failed: no output file")
        progress(99, "done")
        return [
            ProducedFile(
                path=out, ext="mp4", width=width, height=height, duration_s=frames / max(fps, 1)
            )
        ]
