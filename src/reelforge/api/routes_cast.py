"""Cast routes: candidates, approval, library reuse and uploads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from reelforge.api.routes_jobs import job_body
from reelforge.api.schemas import (
    CastActionOut,
    CastApproveRequest,
    CastGenerateRequest,
    CastItemOut,
    CastOut,
    CastUseLibraryRequest,
    JobOut,
)
from reelforge.cast import service, state
from reelforge.cast.backends import probe_backend
from reelforge.cast.licence import licence_warning
from reelforge.cast.uploads import NotAnImage, TooLarge, sniff_image
from reelforge.context import AppContext

NOT_AN_IMAGE = "That file isn't a PNG or JPEG image."


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["cast"])

    def check(project_id: str, key: str | None = None) -> state.StoryCast:
        try:
            return service.require(ctx, project_id, key)
        except service.ProjectMissing:
            raise HTTPException(404, "project not found") from None
        except service.StageLocked:
            raise HTTPException(409, "Approve the story first.") from None
        except service.UnknownCharacter:
            raise HTTPException(404, "character not found") from None

    def item_for(project_id: str, key: str, story: state.StoryCast) -> dict[str, Any]:
        job = service.latest_jobs(ctx, project_id).get(key)
        return service.build_item(
            ctx, story.characters[key], state.get_slot(ctx, project_id, key), job, project_id
        )

    def action_body(project_id: str, key: str) -> JSONResponse:
        story = state.load_story_cast(ctx, project_id)
        slots = state.list_slots(ctx, project_id)
        return JSONResponse(
            {
                "project_stage": service.project_stage(ctx, project_id),
                "approved_count": service.approved_count(story, slots),
                "total": len(story.characters),
                "character": item_for(project_id, key, story),
            }
        )

    @router.get("/{project_id}/cast", response_model=CastOut)
    async def get_cast(project_id: str) -> JSONResponse:
        story = check(project_id)
        slots = state.list_slots(ctx, project_id)
        jobs = service.latest_jobs(ctx, project_id)
        body: dict[str, Any] = {
            "stage": service.project_stage(ctx, project_id),
            "approved_count": service.approved_count(story, slots),
            "total": len(story.characters),
            "image_backend": (await probe_backend(ctx)).as_dict(),
        }
        if "image" in ctx.registry.keys():
            warning = licence_warning(ctx.registry.get("image"))
            if warning is not None:
                body["licence_warning"] = warning
        body["characters"] = [
            service.build_item(ctx, char, slots.get(key), jobs.get(key), project_id)
            for key, char in story.characters.items()
        ]
        return JSONResponse(body)

    @router.post("/{project_id}/cast/{key}:generate", status_code=202, response_model=JobOut)
    async def generate(project_id: str, key: str, body: CastGenerateRequest) -> JSONResponse:
        check(project_id, key)
        active = service.active_job(ctx, project_id, key)
        if active is not None:
            return JSONResponse(job_body(active), status_code=202)
        if body.refine is not None:
            slot = state.get_slot(ctx, project_id, key)
            if slot is None or body.refine.from_candidate not in (slot.candidate_ids or []):
                raise HTTPException(404, "candidate not found")
        if body.look_text is not None:
            service.apply_look_text(ctx, project_id, key, body.look_text)
        job = ctx.queue.enqueue(
            type=state.GENERATE_JOB,
            project_id=project_id,
            payload={
                "key": key,
                "stage": "cast",
                "regenerate": body.regenerate,
                "refine": body.refine.model_dump() if body.refine is not None else None,
                "seed": body.seed,
                "backend": body.backend,
                "total": 1 if body.refine is not None else state.CANDIDATES_PER_RUN,
            },
            heavy=True,
            mem_need_gb=ctx.settings.image_mem_gb,
        )
        return JSONResponse(job_body(job), status_code=202)

    @router.post("/{project_id}/cast/{key}:approve", response_model=CastActionOut)
    async def approve(project_id: str, key: str, body: CastApproveRequest) -> JSONResponse:
        story = check(project_id, key)
        try:
            service.approve(ctx, project_id, key, body.candidate_id, story)
        except service.UnknownCandidate:
            raise HTTPException(404, "candidate not found") from None
        return action_body(project_id, key)

    @router.post("/{project_id}/cast/{key}:reopen", response_model=CastActionOut)
    async def reopen(project_id: str, key: str) -> JSONResponse:
        check(project_id, key)
        service.reopen(ctx, project_id, key)
        return action_body(project_id, key)

    @router.post("/{project_id}/cast/{key}:use-library", response_model=CastActionOut)
    async def use_library(project_id: str, key: str, body: CastUseLibraryRequest) -> JSONResponse:
        check(project_id, key)
        try:
            service.use_library(ctx, project_id, key, body.character_id)
        except service.UnknownCharacter:
            raise HTTPException(404, "That library character no longer exists.") from None
        except service.NoMasterImage:
            raise HTTPException(409, "That library character has no master image.") from None
        return action_body(project_id, key)

    @router.post("/{project_id}/cast/{key}:upload", status_code=201, response_model=CastItemOut)
    async def upload(project_id: str, key: str, file: UploadFile) -> JSONResponse:
        story = check(project_id, key)
        limit_mb = ctx.settings.max_upload_mb
        too_large = HTTPException(413, f"That image is larger than {limit_mb} MB.")
        data = await file.read(limit_mb * 1024 * 1024 + 1)
        if len(data) > limit_mb * 1024 * 1024:
            raise too_large
        try:
            ext, width, height = sniff_image(data)
        except NotAnImage:
            raise HTTPException(415, NOT_AN_IMAGE) from None
        except TooLarge:
            raise too_large from None
        service.store_upload(ctx, project_id, key, data, ext, width, height)
        return JSONResponse(item_for(project_id, key, story), status_code=201)

    return router
