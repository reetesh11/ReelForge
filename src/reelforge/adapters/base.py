"""Adapter protocol and shared types."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from reelforge.models_registry import ModelEntry


class TaskSpec(BaseModel):
    kind: Literal["image", "audio", "video"]
    prompt: str
    seed: int
    params: dict[str, Any]
    model: ModelEntry
    input_paths: list[Path] = []


class ProducedFile(BaseModel):
    path: Path
    ext: str
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None


class HealthReport(BaseModel):
    name: str
    ok: bool
    version: str | None = None
    detail: str


ProgressCb = Callable[[int, str], None]


class AdapterError(Exception):
    """Non-transient adapter failure; the message becomes `job.error`."""


class TransientError(AdapterError):
    """A failure worth one automatic retry."""


class CancelToken:
    """Thread-safe cancel flag that can also be awaited from an event loop."""

    def __init__(self) -> None:
        self._flag = threading.Event()
        self._lock = threading.Lock()
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []

    @property
    def cancelled(self) -> bool:
        return self._flag.is_set()

    def cancel(self) -> None:
        with self._lock:
            self._flag.set()
            waiters = list(self._waiters)
        for loop, event in waiters:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                continue

    async def wait(self) -> None:
        event = asyncio.Event()
        entry = (asyncio.get_running_loop(), event)
        with self._lock:
            self._waiters.append(entry)
            if self._flag.is_set():
                event.set()
        try:
            await event.wait()
        finally:
            with self._lock:
                if entry in self._waiters:
                    self._waiters.remove(entry)


class Adapter(Protocol):
    name: str
    version: str

    async def health(self) -> HealthReport: ...

    async def capabilities(self) -> set[str]: ...

    async def run(
        self,
        task: TaskSpec,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        ctx_job_id: str | None = None,
    ) -> list[ProducedFile]: ...
