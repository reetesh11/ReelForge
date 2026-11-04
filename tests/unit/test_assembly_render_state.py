from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from reelforge.assembly.render_state import RenderHooks, RenderState, commit_part, part_path


class Kill(BaseException):
    pass


def _run(state: RenderState, name: str, out: Path, hooks: RenderHooks | None = None) -> bool:
    async def work() -> None:
        part_path(out).write_text("x")
        commit_part(out)

    return asyncio.run(state.run_step(name, [out], work, hooks))


def test_done_step_with_output_is_skipped(tmp_path: Path) -> None:
    out = tmp_path / "a.txt"
    state = RenderState.open(tmp_path, "h", "preview")
    assert _run(state, "A", out) is True
    state = RenderState.open(tmp_path, "h", "preview")
    assert _run(state, "A", out) is False
    assert state.runs("A") == 1


def test_missing_output_reruns_and_counts(tmp_path: Path) -> None:
    out = tmp_path / "a.txt"
    state = RenderState.open(tmp_path, "h", "preview")
    _run(state, "A", out)
    out.unlink()
    assert _run(RenderState.open(tmp_path, "h", "preview"), "A", out) is True
    assert json.loads((tmp_path / "state.json").read_text())["steps"]["A"]["runs"] == 2


def test_changed_hash_restarts_the_folder_and_part_files_go(tmp_path: Path) -> None:
    out = tmp_path / "a.txt"
    _run(RenderState.open(tmp_path, "h", "preview"), "A", out)
    (tmp_path / "left.part").write_text("junk")
    state = RenderState.open(tmp_path, "other", "preview")
    assert not out.exists() and not (tmp_path / "left.part").exists()
    assert state.steps == {}


def test_kill_before_and_after(tmp_path: Path) -> None:
    out = tmp_path / "a.txt"

    def boom(_: str) -> None:
        raise Kill

    state = RenderState.open(tmp_path, "h", "preview")
    with pytest.raises(Kill):
        _run(state, "A", out, RenderHooks(before_step=boom))
    assert not out.exists()
    state = RenderState.open(tmp_path, "h", "preview")
    with pytest.raises(Kill):
        _run(state, "A", out, RenderHooks(after_step=boom))
    state = RenderState.open(tmp_path, "h", "preview")
    assert state.is_done("A", [out])
