"""Job routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from reelforge.api.schemas import JobOut, JobStatus
from reelforge.context import AppContext
from reelforge.db.models import Job
from reelforge.jobs.queue import JobNotFound, JobStateError


def job_body(job: Job) -> dict[str, Any]:
    """JobOut as JSON; `result` is only present once a job has produced one."""
    body = JobOut.model_validate(job).model_dump(mode="json")
    if body.get("result") is None:
        body.pop("result", None)
    return body


def job_response(job: Job) -> JSONResponse:
    return JSONResponse(job_body(job))


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

    @router.get("", response_model=list[JobOut])
    async def list_jobs(
        status: JobStatus | None = None, project: str | None = None
    ) -> JSONResponse:
        jobs = ctx.queue.list(status=status, project_id=project)
        return JSONResponse([job_body(j) for j in jobs])

    @router.get("/{job_id}", response_model=JobOut)
    async def get_job(job_id: str) -> JSONResponse:
        try:
            return job_response(ctx.queue.get(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None

    async def cancel(job_id: str) -> JSONResponse:
        try:
            return job_response(ctx.queue.cancel(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None
        except JobStateError:
            raise HTTPException(409, "job already finished") from None

    async def retry(job_id: str) -> JSONResponse:
        try:
            return job_response(ctx.queue.retry(job_id))
        except JobNotFound:
            raise HTTPException(404, "job not found") from None
        except JobStateError:
            raise HTTPException(409, "only failed jobs can be retried") from None

    router.add_api_route("/{job_id}/cancel", cancel, methods=["POST"], response_model=JobOut)
    router.add_api_route("/{job_id}:cancel", cancel, methods=["POST"], include_in_schema=False)
    router.add_api_route("/{job_id}/retry", retry, methods=["POST"], response_model=JobOut)
    router.add_api_route("/{job_id}:retry", retry, methods=["POST"], include_in_schema=False)
    return router
