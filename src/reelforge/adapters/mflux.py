"""mflux adapter: runs the mflux command line through the shared runner (no shell)."""

from __future__ import annotations

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

DEFAULT_WIDTH = 576
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 4
DEFAULT_STRENGTH = 0.6


class MfluxAdapter:
    name = "mflux"
    version = "mflux-1"

    def __init__(self, command: Path | str, *, timeout_s: float = 600.0) -> None:
        self.command = str(command)
        self.timeout_s = timeout_s

    async def health(self) -> HealthReport:
        ok = Path(self.command).is_file()
        return HealthReport(
            name=self.name,
            ok=ok,
            version=self.version,
            detail="mflux command found" if ok else f"mflux command not found: {self.command}",
        )

    async def capabilities(self) -> set[str]:
        return {"image"}

    async def run(
        self,
        task: TaskSpec,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        ctx_job_id: str | None = None,
    ) -> list[ProducedFile]:
        params = task.params
        width = int(params.get("width", DEFAULT_WIDTH))
        height = int(params.get("height", DEFAULT_HEIGHT))
        steps = int(params.get("steps", DEFAULT_STEPS))
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "out.png"
        argv = [
            self.command,
            "--model", task.model.id,
            "--prompt", task.prompt,
            "--seed", str(task.seed),
            "--width", str(width),
            "--height", str(height),
            "--steps", str(steps),
            "--output", str(out),
        ]  # fmt: skip
        if task.input_paths:
            strength = params.get("strength", DEFAULT_STRENGTH)
            argv += ["--image-path", str(task.input_paths[0]), "--image-strength", str(strength)]
        progress(1, "starting mflux")
        result = await run_command(argv, timeout_s=self.timeout_s, cancel=cancel, job_id=ctx_job_id)
        if result.cancelled:
            raise AdapterError("cancelled")
        if result.timed_out:
            raise AdapterError(result.error or "mflux timed out")
        if result.exit_code != 0:
            detail = result.error or f"exit code {result.exit_code}"
            raise AdapterError(f"mflux failed: {detail}")
        if not out.is_file():
            raise AdapterError("mflux produced no image")
        progress(99, "done")
        return [ProducedFile(path=out, ext="png", width=width, height=height)]
