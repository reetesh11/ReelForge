"""Memory pre-flight for heavy jobs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import psutil


@dataclass
class PreflightResult:
    ok: bool
    free_gb: float
    need_gb: float
    reason: str | None


def default_available_gb() -> float:
    return psutil.virtual_memory().available / 1024**3


async def preflight(
    need_gb: float,
    *,
    available_gb: Callable[[], float] = default_available_gb,
    unload_ollama: Callable[[], Awaitable[None]],
    wait_s: float,
    poll_s: float = 0.5,
    on_wait: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> PreflightResult:
    """Free memory (unload Ollama), then wait up to `wait_s` for `need_gb` to be available."""
    await unload_ollama()
    deadline = time.monotonic() + wait_s
    while True:
        free = available_gb()
        if free >= need_gb:
            return PreflightResult(True, free, need_gb, None)
        reason = f"Only {free:.1f} GB free, job needs {need_gb:.1f} GB."
        remaining = deadline - time.monotonic()
        if remaining <= 0 or (should_stop is not None and should_stop()):
            return PreflightResult(False, free, need_gb, reason)
        if on_wait is not None:
            on_wait(reason)
        await asyncio.sleep(min(poll_s, remaining))
