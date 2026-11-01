"""In-process asyncio worker draining the persistent queue."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from reelforge.adapters.base import AdapterError, CancelToken, TransientError
from reelforge.adapters.runner import CommandResult, current_log_path, current_observer
from reelforge.artifacts.service import generate_artifact
from reelforge.db.models import Job, utcnow
from reelforge.jobs.preflight import preflight
from reelforge.story.structure import structure_story

if TYPE_CHECKING:
    from reelforge.context import AppContext

log = structlog.get_logger()

Handler = Callable[["AppContext", Job, Callable[[int, str], None], CancelToken], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "artifact.generate": generate_artifact,
    "story.structure": structure_story,
}
MAX_ATTEMPTS = 2


class _Observer:
    """Persists the child pid/command as soon as a command starts, and tracks peak RSS."""

    def __init__(self, ctx: AppContext, job_id: str) -> None:
        self.ctx = ctx
        self.job_id = job_id
        self.command: list[str] | None = None
        self.peak_rss_mb = 0.0
        self.exit_code: int | None = None

    def started(self, argv: list[str], pid: int) -> None:
        self.command = argv
        self.ctx.queue.update_running(self.job_id, pid=pid, command=argv)

    def finished(self, result: CommandResult) -> None:
        self.peak_rss_mb = max(self.peak_rss_mb, result.peak_rss_mb)
        self.exit_code = result.exit_code


class Worker:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._main: asyncio.Task[None] | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._heavy_active = False
        self._shutting_down = False

    async def start(self) -> None:
        if self._main is None:
            self._shutting_down = False
            self.ctx.lease.lock = asyncio.Lock()
            self._main = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._shutting_down = True
        if self._main is not None:
            self._main.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main
            self._main = None
        for job_id in list(self._tasks):
            token = self.ctx.queue.tokens.get(job_id)
            if token is not None:
                token.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def wait_idle(self, timeout_s: float = 30.0) -> None:
        async def idle() -> None:
            while self.ctx.queue.list(status="queued") or self.ctx.queue.list(status="running"):
                await asyncio.sleep(0.05)

        try:
            await asyncio.wait_for(idle(), timeout_s)
        except TimeoutError:
            raise TimeoutError("jobs still queued or running") from None

    async def _loop(self) -> None:
        poll = self.ctx.settings.worker_poll_s
        while True:
            try:
                self._dispatch()
            except Exception:  # noqa: BLE001
                log.exception("worker.dispatch_failed")
            await asyncio.sleep(poll)

    def _dispatch(self) -> None:
        light_running = sum(1 for t in self._tasks.values() if not t.done()) - int(
            self._heavy_active
        )
        for job in self.ctx.queue.next_queued():
            if job.id in self._tasks:
                continue
            if job.heavy:
                if self._heavy_active:
                    continue
                self._heavy_active = True
            else:
                if light_running >= self.ctx.settings.max_light_jobs:
                    continue
                light_running += 1
            task = asyncio.create_task(self._run_job(job))
            self._tasks[job.id] = task
            task.add_done_callback(lambda _t, jid=job.id, heavy=job.heavy: self._done(jid, heavy))

    def _done(self, job_id: str, heavy: bool) -> None:
        self._tasks.pop(job_id, None)
        if heavy:
            self._heavy_active = False

    async def _run_job(self, job: Job) -> None:
        try:
            if job.heavy:
                await self._run_heavy(job)
            else:
                await self._execute(job)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("worker.job_crashed", job_id=job.id)
            self.ctx.queue.transition(
                job.id, ("queued", "running"), status="failed", error="internal error",
                finished_at=utcnow(),
            )  # fmt: skip

    async def _run_heavy(self, job: Job) -> None:
        ctx = self.ctx
        lease = ctx.lease
        async with lease.lock:
            last_message: list[str] = [""]

            def on_wait(reason: str) -> None:
                if reason != last_message[0]:
                    last_message[0] = reason
                    ctx.queue.transition(job.id, "queued", message=reason)

            result = await preflight(
                job.mem_need_gb,
                available_gb=ctx.available_gb,
                unload_ollama=ctx.ollama_unload,
                wait_s=ctx.settings.preflight_wait_s,
                poll_s=min(0.5, max(ctx.settings.worker_poll_s, 0.05)),
                on_wait=on_wait,
                should_stop=lambda: ctx.queue.get(job.id).status != "queued",
            )
            if not result.ok:
                ctx.queue.transition(
                    job.id,
                    "queued",
                    status="failed",
                    error=result.reason,
                    message=result.reason,
                    finished_at=utcnow(),
                )
                return
            async with lease.hold(job.id, locked=True):
                await self._execute(job)

    async def _execute(self, job: Job) -> None:
        ctx = self.ctx
        queue = ctx.queue
        rel_log = f"logs/jobs/{job.id}.log"
        abs_log = ctx.settings.data_root / rel_log
        if not queue.transition(
            job.id,
            "queued",
            status="running",
            started_at=utcnow(),
            message=None,
            progress=0,
            log_path=rel_log,
            pid=None,
        ):
            return  # cancelled while queued
        abs_log.parent.mkdir(parents=True, exist_ok=True)
        with abs_log.open("a", encoding="utf-8") as fh:
            fh.write(f"# job {job.id} type={job.type} started {utcnow().isoformat()}\n")

        token = CancelToken()
        queue.tokens[job.id] = token
        observer = _Observer(ctx, job.id)
        current_observer.set(observer)
        current_log_path.set(abs_log)
        last = [0]

        def progress(pct: int, message: str) -> None:
            pct = max(0, min(100, int(pct)))
            if pct > last[0]:
                last[0] = pct
                queue.update_running(job.id, progress=pct, message=message)

        handler = HANDLERS.get(job.type)
        attempts = queue.get(job.id).attempts + 1
        try:
            if handler is None:
                raise AdapterError("unknown job type")
            await handler(ctx, queue.get(job.id), progress, token)
        except asyncio.CancelledError:
            if not self._shutting_down:
                queue.transition(
                    job.id, "running", status="cancelled", finished_at=utcnow(), pid=None
                )
            raise
        except TransientError as exc:
            if token.cancelled:
                self._cancelled(job.id)
            elif attempts < MAX_ATTEMPTS:
                queue.transition(
                    job.id,
                    "running",
                    status="queued",
                    attempts=attempts,
                    message="retrying",
                    error=None,
                    pid=None,
                    started_at=None,
                    progress=0,
                )
            else:
                self._failed(job.id, attempts, str(exc), observer)
        except AdapterError as exc:
            if token.cancelled:
                self._cancelled(job.id)
            else:
                self._failed(job.id, attempts, str(exc), observer)
        except Exception as exc:  # noqa: BLE001
            log.exception("worker.handler_failed", job_id=job.id)
            self._failed(job.id, attempts, f"{type(exc).__name__}: {exc}", observer)
        else:
            queue.transition(
                job.id,
                "running",
                status="succeeded",
                progress=100,
                attempts=attempts,
                finished_at=utcnow(),
                peak_rss_mb=observer.peak_rss_mb,
                exit_code=0,
                command=observer.command,
                pid=None,
                message=None,
                error=None,
            )
        finally:
            queue.tokens.pop(job.id, None)

    def _cancelled(self, job_id: str) -> None:
        self.ctx.queue.transition(
            job_id, "running", status="cancelled", finished_at=utcnow(), pid=None
        )

    def _failed(self, job_id: str, attempts: int, error: str, observer: _Observer) -> None:
        self.ctx.queue.transition(
            job_id,
            "running",
            status="failed",
            attempts=attempts,
            error=error,
            finished_at=utcnow(),
            peak_rss_mb=observer.peak_rss_mb,
            exit_code=observer.exit_code,
            command=observer.command,
            pid=None,
        )
