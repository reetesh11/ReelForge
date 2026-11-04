"""Server-side debounce: a burst of edits becomes one `assemble_preview` job."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import structlog

from reelforge.assembly.build import assembly_dir, working_edl_path
from reelforge.assembly.edl import edl_hash, load_edl, save_edl
from reelforge.assembly.jobs import PREVIEW_JOB
from reelforge.assembly.state import AssemblyError
from reelforge.db.models import Job
from reelforge.jobs.queue import JobStateError

if TYPE_CHECKING:
    from reelforge.context import AppContext

log = structlog.get_logger()


class PreviewScheduler:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._lock = threading.Lock()
        self._timers: dict[str, tuple[threading.Timer, float]] = {}

    def touch(self, project_id: str) -> None:
        """Restart the debounce timer of the project."""
        delay = max(0.0, float(self.ctx.settings.preview_debounce_s))
        with self._lock:
            old = self._timers.pop(project_id, None)
            if old is not None:
                old[0].cancel()
            timer = threading.Timer(delay, self._fire, args=(project_id,))
            timer.daemon = True
            self._timers[project_id] = (timer, time.monotonic() + delay)
            timer.start()

    def remaining(self, project_id: str) -> float | None:
        """Seconds until the pending rebuild fires, None when no timer runs."""
        with self._lock:
            entry = self._timers.get(project_id)
        if entry is None:
            return None
        return max(0.0, entry[1] - time.monotonic())

    def cancel_all(self) -> None:
        with self._lock:
            for timer, _ in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def _fire(self, project_id: str) -> None:
        with self._lock:
            self._timers.pop(project_id, None)
        try:
            self.enqueue_now(project_id)
        except Exception:  # noqa: BLE001
            log.exception("assembly.preview_schedule_failed", project_id=project_id)

    def snapshot(self, project_id: str) -> str:
        """Copy the working EDL to `edls/<hash>.json`; returns the hash."""
        path = working_edl_path(self.ctx, project_id)
        if not path.is_file():
            raise AssemblyError(404, "edl not built")
        edl = load_edl(path)
        digest = edl_hash(edl)
        snap = assembly_dir(self.ctx, project_id) / "edls" / f"{digest}.json"
        if not snap.is_file():
            save_edl(edl, snap)
        return digest

    def enqueue_now(self, project_id: str) -> Job:
        """Snapshot the working EDL and queue one preview, replacing any queued one."""
        with self._lock:
            pending = self._timers.pop(project_id, None)
            if pending is not None:
                pending[0].cancel()
        digest = self.snapshot(project_id)
        queue = self.ctx.queue
        for job in queue.list(status="queued", project_id=project_id):
            if job.type == PREVIEW_JOB:
                try:
                    queue.cancel(job.id)
                except JobStateError:
                    pass
        return queue.enqueue(
            type=PREVIEW_JOB,
            project_id=project_id,
            payload={"stage": "assembly", "kind": "preview", "edl_hash": digest},
            heavy=False,
            mem_need_gb=0.0,
        )
