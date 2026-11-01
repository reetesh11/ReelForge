"""Job routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from reelforge.api.schemas import JobOut, JobStatus
from reelforge.context import AppContext
from reelforge.jobs.queue import JobNotFound, JobStateError


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

    @router.get("")
    async def list_jobs(
        status: JobStatus | None = None, project: str | None = None
    ) -> list[JobOut]:
        return [JobOut.model_validate(j) for j in ctx.queue.list(status=status, project_id=project)]

    @router.get("/{job_id}")
    async def get_job(job_id: str) -> JobOut:
        try:
            return JobOut.model_validate(ctx.queue.get(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None

    async def cancel(job_id: str) -> JobOut:
        try:
            return JobOut.model_validate(ctx.queue.cancel(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None
        except JobStateError:
            raise HTTPException(409, "job already finished") from None

    async def retry(job_id: str) -> JobOut:
        try:
            return JobOut.model_validate(ctx.queue.retry(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None
        except JobStateError:
            raise HTTPException(409, "only failed jobs can be retried") from None

    router.add_api_route("/{job_id}/cancel", cancel, methods=["POST"])
    router.add_api_route("/{job_id}:cancel", cancel, methods=["POST"], include_in_schema=False)
    router.add_api_route("/{job_id}/retry", retry, methods=["POST"])
    router.add_api_route("/{job_id}:retry", retry, methods=["POST"], include_in_schema=False)
    return router
