"""Single GPU lease: one heavy job at a time, recorded in the `settings` table."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from reelforge.db.models import Setting, utcnow

GPU_LEASE_KEY = "gpu_lease"


class GpuLease:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, job_id: str, *, locked: bool = False) -> AsyncGenerator[None]:
        """Hold the lease. Pass `locked=True` when the caller already holds `self.lock`."""
        if locked:
            async with self._record(job_id):
                yield
        else:
            async with self.lock, self._record(job_id):
                yield

    @asynccontextmanager
    async def _record(self, job_id: str) -> AsyncGenerator[None]:
        value = {"job_id": job_id, "pid": os.getpid(), "since": utcnow().isoformat()}
        with self.session_factory.begin() as s:
            s.merge(Setting(key=GPU_LEASE_KEY, value=value))
        try:
            yield
        finally:
            self.clear()

    def holder(self) -> str | None:
        with self.session_factory() as s:
            row = s.get(Setting, GPU_LEASE_KEY)
            value = row.value if row is not None else None
        if isinstance(value, dict):
            job_id = value.get("job_id")  # type: ignore[reportUnknownMemberType]
            return str(job_id) if job_id else None  # type: ignore[reportUnknownArgumentType]
        return None

    def clear(self) -> None:
        with self.session_factory.begin() as s:
            s.execute(delete(Setting).where(Setting.key == GPU_LEASE_KEY))
