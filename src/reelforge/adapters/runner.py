"""The single place that executes external commands (argument lists, never a shell)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil
import structlog

from reelforge.adapters.base import CancelToken
from reelforge.jobs.classify import classify_exit

log = structlog.get_logger()

CANCEL_GRACE_S = 2.0


class RunObserver(Protocol):
    """Receives command lifecycle events (the worker uses it to persist pid, command, RSS)."""

    def started(self, argv: list[str], pid: int) -> None: ...

    def finished(self, result: CommandResult) -> None: ...


current_observer: ContextVar[RunObserver | None] = ContextVar("current_observer", default=None)
current_log_path: ContextVar[Path | None] = ContextVar("current_log_path", default=None)


@dataclass
class CommandResult:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool
    peak_rss_mb: float
    duration_s: float
    error: str | None


def _fmt_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _tree(pid: int) -> list[psutil.Process]:
    try:
        root = psutil.Process(pid)
        return [root, *root.children(recursive=True)]
    except psutil.Error:
        return []


def _signal_tree(pid: int, kill: bool) -> None:
    for proc in _tree(pid):
        with contextlib.suppress(psutil.Error):
            proc.kill() if kill else proc.terminate()


def _rss_mb(pid: int) -> float:
    total = 0
    for proc in _tree(pid):
        with contextlib.suppress(psutil.Error):
            total += proc.memory_info().rss
    return total / (1024 * 1024)


async def _sample(pid: int, interval: float, peak: list[float]) -> None:
    while True:
        peak[0] = max(peak[0], _rss_mb(pid))
        await asyncio.sleep(interval)


def _append_log(path: Path, result: CommandResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"$ {json.dumps(result.argv)}\n")
        if result.stdout:
            fh.write(f"--- stdout ---\n{result.stdout}\n")
        if result.stderr:
            fh.write(f"--- stderr ---\n{result.stderr}\n")
        fh.write(
            f"--- exit code: {result.exit_code}  peak rss: {result.peak_rss_mb:.1f} MB"
            f"  duration: {result.duration_s:.2f}s"
            f"{'  ' + result.error if result.error else ''} ---\n"
        )


async def run_command(
    argv: Sequence[str],
    *,
    timeout_s: float,
    cancel: CancelToken | None = None,
    on_start: Callable[[int], None] | None = None,
    sample_interval_s: float = 2.0,
    log_path: Path | None = None,
    job_id: str | None = None,
) -> CommandResult:
    args = [str(a) for a in argv]
    log.info("adapter.command", argv=args, timeout_s=timeout_s, job_id=job_id)
    started = time.monotonic()
    observer = current_observer.get()
    target_log = log_path or current_log_path.get()
    peak = [0.0]
    timed_out = cancelled = False
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        result = CommandResult(
            args,
            None,
            "",
            "",
            False,
            False,
            0.0,
            time.monotonic() - started,
            f"cannot start: {exc}",
        )
        if target_log:
            _append_log(target_log, result)
        if observer:
            observer.finished(result)
        return result

    if on_start:
        on_start(proc.pid)
    if observer:
        observer.started(args, proc.pid)
    sampler = asyncio.create_task(_sample(proc.pid, sample_interval_s, peak))
    comm = asyncio.create_task(proc.communicate())
    waiters: set[asyncio.Task[object]] = {comm}  # type: ignore[arg-type]
    cancel_task: asyncio.Task[None] | None = None
    if cancel is not None:
        cancel_task = asyncio.create_task(cancel.wait())
        waiters.add(cancel_task)  # type: ignore[arg-type]
    try:
        await asyncio.wait(waiters, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED)
        if not comm.done():
            if cancel_task is not None and cancel_task.done():
                cancelled = True
                _signal_tree(proc.pid, kill=False)
                try:
                    await asyncio.wait_for(asyncio.shield(comm), CANCEL_GRACE_S)
                except TimeoutError:
                    _signal_tree(proc.pid, kill=True)
            else:
                timed_out = True
                _signal_tree(proc.pid, kill=True)
            await comm
    finally:
        sampler.cancel()
        if cancel_task is not None:
            cancel_task.cancel()
        if not comm.done():
            _signal_tree(proc.pid, kill=True)
            comm.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sampler
    out_b, err_b = comm.result()
    await proc.wait()
    code = proc.returncode
    error = f"timed out after {_fmt_seconds(timeout_s)}s" if timed_out else classify_exit(code)
    if cancelled:
        error = "cancelled"
    result = CommandResult(
        argv=args,
        exit_code=code,
        stdout=out_b.decode("utf-8", "replace"),
        stderr=err_b.decode("utf-8", "replace"),
        timed_out=timed_out,
        cancelled=cancelled,
        peak_rss_mb=peak[0],
        duration_s=time.monotonic() - started,
        error=error,
    )
    if target_log:
        _append_log(target_log, result)
    if observer:
        observer.finished(result)
    return result
