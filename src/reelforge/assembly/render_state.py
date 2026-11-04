"""Resumable render state: `state.json` in the render folder, one entry per finished step."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

STATE_FILE = "state.json"


@dataclass
class RenderHooks:
    """Called around each step; tests raise a BaseException from them to simulate a kill."""

    before_step: Callable[[str], None] | None = None
    after_step: Callable[[str], None] | None = None


def part_path(path: Path) -> Path:
    """The scratch name a step writes before renaming to `path`."""
    return path.with_name(path.name + ".part")


def commit_part(path: Path) -> None:
    os.replace(part_path(path), path)


def clear_folder(folder: Path) -> None:
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


class RenderState:
    def __init__(self, folder: Path, edl_hash: str, profile: str) -> None:
        self.folder = folder
        self.path = folder / STATE_FILE
        self.edl_hash = edl_hash
        self.profile = profile
        self.steps: dict[str, dict[str, Any]] = {}
        self.meta: dict[str, Any] = {}

    @classmethod
    def open(cls, folder: Path, edl_hash: str, profile: str) -> RenderState:
        """Load the saved state; a different EDL or profile (or a bad file) restarts the folder."""
        folder.mkdir(parents=True, exist_ok=True)
        state = cls(folder, edl_hash, profile)
        data: dict[str, Any] | None
        try:
            loaded: Any = json.loads(state.path.read_text(encoding="utf-8"))
            data = cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else None
        except (OSError, ValueError):
            data = None
        if (
            data is not None
            and data.get("edl_hash") == edl_hash
            and data.get("profile") == profile
            and isinstance(data.get("steps"), dict)
        ):
            state.steps = dict(data["steps"])
            state.meta = dict(data.get("meta") or {})
        else:
            clear_folder(folder)
        for stale in folder.rglob("*.part"):
            stale.unlink(missing_ok=True)
        state.save()
        return state

    def save(self) -> None:
        body = {
            "edl_hash": self.edl_hash,
            "profile": self.profile,
            "steps": self.steps,
            "meta": self.meta,
        }
        tmp = self.path.with_name(STATE_FILE + ".part")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def runs(self, name: str) -> int:
        return int(self.steps.get(name, {}).get("runs", 0))

    def is_done(self, name: str, outputs: Sequence[Path]) -> bool:
        entry = self.steps.get(name)
        return bool(entry and entry.get("done")) and all(p.exists() for p in outputs)

    async def run_step(
        self,
        name: str,
        outputs: Sequence[Path],
        fn: Callable[[], Awaitable[None]],
        hooks: RenderHooks | None = None,
    ) -> bool:
        """Run `fn` unless the step is already done with its outputs present; True when it ran."""
        if self.is_done(name, outputs):
            return False
        if hooks is not None and hooks.before_step is not None:
            hooks.before_step(name)
        await fn()
        self.steps[name] = {"done": True, "runs": self.runs(name) + 1}
        self.save()
        if hooks is not None and hooks.after_step is not None:
            hooks.after_step(name)
        return True
