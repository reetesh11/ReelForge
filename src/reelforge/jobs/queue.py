"""Persistent job queue backed by SQLite."""

from __future__ import annotations

import contextlib
from typing import Any, Protocol, cast

import psutil
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from reelforge.adapters.base import CancelToken
from reelforge.db.models import Job, Setting, utcnow
from reelforge.events import EventBus

GPU_LEASE_KEY = "gpu_lease"
FINISHED = ("succeeded", "failed", "cancelled")


class JobNotFound(Exception):
    pass


class JobStateError(Exception):
    pass


class _Clearable(Protocol):
    def clear(self) -> None: ...


class JobQueue:
    def __init__(self, session_factory: sessionmaker[Session], bus: EventBus | None = None) -> None:
        self.session_factory = session_factory
        self.bus = bus
        self.tokens: dict[str, CancelToken] = {}

    def _publish(self, job: Job) -> None:
        if self.bus is not None:
            self.bus.publish(
                "job.updated",
                {
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "status": job.status,
                    "progress": job.progress,
                    "eta_s": None,
                    "message": job.message,
                    "error": job.error,
                },
            )

    def enqueue(
        self,
        *,
        type: str,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
        heavy: bool = False,
        mem_need_gb: float = 0.0,
        priority: int = 0,
    ) -> Job:
        job = Job(
            type=type,
            project_id=project_id,
            payload=payload or {},
            heavy=heavy,
            mem_need_gb=mem_need_gb,
            priority=priority,
            status="queued",
            attempts=0,
            progress=0,
            created_at=utcnow(),
        )
        with self.session_factory.begin() as s:
            s.add(job)
        self._publish(job)
        return job

    def get(self, job_id: str) -> Job:
        with self.session_factory() as s:
            job = s.get(Job, job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    def list(self, *, status: str | None = None, project_id: str | None = None) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
        if status is not None:
            stmt = stmt.where(Job.status == status)
        if project_id is not None:
            stmt = stmt.where(Job.project_id == project_id)
        with self.session_factory() as s:
            return list(s.scalars(stmt))

    def next_queued(self, limit: int = 50) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.priority.desc(), Job.created_at, Job.id)
            .limit(limit)
        )
        with self.session_factory() as s:
            return list(s.scalars(stmt))

    def transition(self, job_id: str, from_status: str | tuple[str, ...], **values: Any) -> bool:
        """Compare-and-set on `status`; returns True when this call applied the change."""
        froms = (from_status,) if isinstance(from_status, str) else from_status
        with self.session_factory.begin() as s:
            result = s.execute(
                update(Job).where(Job.id == job_id, Job.status.in_(froms)).values(**values)
            )
            applied = cast("CursorResult[Any]", result).rowcount > 0
            job = s.get(Job, job_id) if applied else None
        if job is not None:
            self._publish(job)
        return applied

    def update_running(self, job_id: str, **values: Any) -> None:
        """Update fields of a running job (progress, message, pid, command...)."""
        self.transition(job_id, "running", **values)

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status in FINISHED:
            raise JobStateError("job already finished")
        if job.status == "queued":
            if self.transition(job_id, "queued", status="cancelled", finished_at=utcnow()):
                return self.get(job_id)
            job = self.get(job_id)
            if job.status in FINISHED:
                raise JobStateError("job already finished")
        token = self.tokens.get(job_id)
        if token is not None:
            token.cancel()
        else:
            self.transition(job_id, "running", status="cancelled", finished_at=utcnow(), pid=None)
        return self.get(job_id)

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status != "failed":
            raise JobStateError("only failed jobs can be retried")
        applied = self.transition(
            job_id,
            "failed",
            status="queued",
            attempts=0,
            error=None,
            progress=0,
            exit_code=None,
            message=None,
            pid=None,
            started_at=None,
            finished_at=None,
        )
        if not applied:
            raise JobStateError("only failed jobs can be retried")
        return self.get(job_id)

    def recover_orphans(self, lease: _Clearable | None = None) -> list[str]:
        with self.session_factory() as s:
            running = list(
                s.scalars(select(Job).where(Job.status == "running").order_by(Job.created_at))
            )
        recovered: list[str] = []
        for job in running:
            _terminate_if_ours(job.pid, job.command)
            if self.transition(
                job.id,
                "running",
                status="queued",
                pid=None,
                started_at=None,
                progress=0,
                message="recovered after restart",
            ):
                recovered.append(job.id)
        with self.session_factory.begin() as s:
            s.execute(delete(Setting).where(Setting.key == GPU_LEASE_KEY))
        if lease is not None:
            lease.clear()
        return recovered


def _terminate_if_ours(pid: int | None, command: list[Any] | None) -> None:
    if not pid or not command:
        return
    with contextlib.suppress(psutil.Error):
        proc = psutil.Process(pid)
        if proc.cmdline() == [str(c) for c in command]:
            for child in proc.children(recursive=True):
                with contextlib.suppress(psutil.Error):
                    child.kill()
            proc.kill()
