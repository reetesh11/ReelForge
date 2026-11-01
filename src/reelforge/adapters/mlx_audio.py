"""mlx-audio adapter (M1: presence check only; never loads a model)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from reelforge.adapters.base import HealthReport


class MlxAudioAdapter:
    name = "mlx_audio"

    def __init__(self, project_path: Path | None) -> None:
        self.project_path = project_path

    def check(self) -> HealthReport:
        if self.project_path is None:
            return HealthReport(name=self.name, ok=False, detail="mlx-audio path is not configured")
        if not self.project_path.is_dir():
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"mlx-audio project not found at {self.project_path}",
            )
        if not (self.project_path / ".venv").is_dir():
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"mlx-audio has no virtual environment in {self.project_path}",
            )
        return HealthReport(name=self.name, ok=True, detail=f"mlx-audio at {self.project_path}")

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)
