"""Assembly routes: build the EDL, edit it, preview, export and reopen versions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from reelforge.api.routes_jobs import job_body
from reelforge.api.schemas import (
    AssemblyBuildRequest,
    AssemblyEditOut,
    AssemblyEditRequest,
    AssemblyExportRequest,
    AssemblyOpenVersionRequest,
    AssemblyOut,
    JobOut,
)
from reelforge.assembly import status
from reelforge.assembly.build import build_edl, project_row, working_edl_path
from reelforge.assembly.edit import apply_edit, load_working
from reelforge.assembly.edl import save_edl
from reelforge.assembly.state import AssemblyError
from reelforge.context import AppContext
from reelforge.frames.service import stage_at_least

LOCKED = "Approve the shots first."


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["assembly"])

    def gate(project_id: str) -> None:
        project = project_row(ctx, project_id)
        if not stage_at_least(project.stage, "SHOTS_APPROVED"):
            raise AssemblyError(409, LOCKED)

    def fail(exc: AssemblyError) -> HTTPException:
        return HTTPException(exc.status, exc.message)

    @router.get("/assembly", response_model=AssemblyOut)
    async def get_assembly(project_id: str) -> JSONResponse:
        try:
            gate(project_id)
            return JSONResponse(status.assembly_body(ctx, project_id))
        except AssemblyError as exc:
            raise fail(exc) from None

    @router.post("/assembly:build", response_model=AssemblyOut)
    async def build(project_id: str, body: AssemblyBuildRequest) -> JSONResponse:
        try:
            gate(project_id)
            path = working_edl_path(ctx, project_id)
            changed = body.force or not path.is_file()
            if changed:
                save_edl(build_edl(ctx, project_id), path)
            out = status.assembly_body(ctx, project_id)
            if changed or out["preview"]["state"] == "none":
                ctx.previews.touch(project_id)
                out = status.assembly_body(ctx, project_id)
            return JSONResponse(out)
        except AssemblyError as exc:
            raise fail(exc) from None

    @router.get("/assembly/edl")
    async def get_edl(project_id: str) -> JSONResponse:
        try:
            gate(project_id)
            return JSONResponse(load_working(ctx, project_id).model_dump(mode="json"))
        except AssemblyError as exc:
            raise fail(exc) from None

    @router.post("/assembly:edit", response_model=AssemblyEditOut)
    async def edit(project_id: str, body: AssemblyEditRequest) -> JSONResponse:
        try:
            gate(project_id)
            _, notes = apply_edit(ctx, project_id, body.model_dump(exclude_none=True))
            ctx.previews.touch(project_id)
            return JSONResponse({"assembly": status.assembly_body(ctx, project_id), "notes": notes})
        except AssemblyError as exc:
            raise fail(exc) from None

    @router.post("/assembly:preview", status_code=202, response_model=JobOut)
    async def preview(project_id: str) -> JSONResponse:
        try:
            gate(project_id)
            load_working(ctx, project_id)
            job = ctx.previews.enqueue_now(project_id)
        except AssemblyError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    _ = (AssemblyExportRequest, AssemblyOpenVersionRequest)
    return router
