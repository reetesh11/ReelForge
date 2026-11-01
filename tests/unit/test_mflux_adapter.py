"""mflux adapter: argv exactness, failure, cancel and no shell."""

from __future__ import annotations

import asyncio
import json
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec
from reelforge.adapters.mflux import MfluxAdapter
from reelforge.models_registry import ModelEntry


def _task(inputs: list[Path] | None = None, **params: Any) -> TaskSpec:
    model = ModelEntry(key="image", id="m-id", revision="r", license="mit")
    return TaskSpec(
        kind="image", prompt="p", seed=4, params=params, model=model, input_paths=inputs or []
    )


def _script(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


WRITE = (
    "import sys, json\n"
    "a = sys.argv[1:]\n"
    "open(sys.argv[0] + '.log', 'w').write(json.dumps(a))\n"
    "open(a[a.index('--output') + 1], 'wb').write(b'x')\n"
)


async def test_argv_is_exact_and_uses_exec(tmp_path, monkeypatch):
    cmd = _script(tmp_path / "fake", WRITE)
    real = asyncio.create_subprocess_exec
    seen: list[tuple[Any, ...]] = []

    async def spy(*args: Any, **kw: Any):
        seen.append(args)
        return await real(*args, **kw)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    out_dir = tmp_path / "o"
    produced = await MfluxAdapter(cmd).run(
        _task(width=64, height=96, steps=2), out_dir, lambda p, m: None, CancelToken()
    )
    argv = json.loads((tmp_path / "fake.log").read_text())
    assert argv == [
        "--model", "m-id", "--prompt", "p", "--seed", "4", "--width", "64",
        "--height", "96", "--steps", "2", "--output", str(out_dir / "out.png"),
    ]  # fmt: skip
    assert seen and seen[0][0] == str(cmd)
    assert produced[0].path == out_dir / "out.png" and (produced[0].width, produced[0].height) == (
        64,
        96,
    )


async def test_nonzero_exit_raises(tmp_path):
    cmd = _script(tmp_path / "bad", "raise SystemExit(3)\n")
    with pytest.raises(AdapterError):
        await MfluxAdapter(cmd).run(_task(), tmp_path / "o", lambda p, m: None, CancelToken())


async def test_cancel_raises_cancelled(tmp_path):
    cmd = _script(tmp_path / "slow", "import time\ntime.sleep(30)\n")
    token = CancelToken()
    asyncio.get_running_loop().call_later(0.3, token.cancel)
    with pytest.raises(AdapterError, match="cancelled"):
        await MfluxAdapter(cmd).run(_task(), tmp_path / "o", lambda p, m: None, token)
