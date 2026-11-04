"""Frames routes: the key frame board, generation, takes, prompts and uploads."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from reelforge.api.routes_jobs import job_body
from reelforge.api.schemas import (
    FrameActionOut,
    FrameContinueRequest,
    FrameSavePromptRequest,
    FramesCancelOut,
    FrameSetFramingRequest,
    FramesGenerateOut,
    FramesGenerateRequest,
    FramesOut,
    JobOut,
    VoiceSelectTakeRequest,
)
from reelforge.context import AppContext
from reelforge.frames import service


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["frames"])

    def fail(exc: service.FrameError) -> HTTPException:
        return HTTPException(exc.status, exc.message)

    @router.get("/frames", response_model=FramesOut)
    async def get_frames(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.frames_body(ctx, project_id))
        except service.FrameError as exc:
            raise fail(exc) from None

    @router.post("/frames:generate", status_code=202, response_model=FramesGenerateOut)
    async def generate(project_id: str, body: FramesGenerateRequest) -> JSONResponse:
        try:
            jobs, skipped = service.enqueue_generation(ctx, project_id, body.mode, body.scenes)
        except service.FrameError as exc:
            raise fail(exc) from None
        return JSONResponse({"jobs": [job_body(j) for j in jobs], "skipped": skipped}, 202)

    @router.post("/frames:cancel", response_model=FramesCancelOut)
    async def cancel(project_id: str) -> JSONResponse:
        try:
            return JSONResponse({"cancelled": service.cancel_all(ctx, project_id)})
        except service.FrameError as exc:
            raise fail(exc) from None

    sc = "/frames/{scene_id}"

    @router.post(sc + ":generate", status_code=202, response_model=JobOut)
    async def generate_one(project_id: str, scene_id: str) -> JSONResponse:
        try:
            job = service.enqueue_scene(ctx, project_id, scene_id)
        except service.FrameError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    def action(name: str, status: int = 200):  # noqa: ANN202
        return router.post(f"{sc}:{name}", status_code=status, response_model=FrameActionOut)

    @action("approve")
    async def approve(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.approve(ctx, project_id, scene_id))
        except service.FrameError as exc:
            raise fail(exc) from None

    @action("select-take")
    async def select_take(
        project_id: str, scene_id: str, body: VoiceSelectTakeRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.select_take(ctx, project_id, scene_id, body.take_id))
        except service.FrameError as exc:
            raise fail(exc) from None

    @action("set-framing")
    async def set_framing(
        project_id: str, scene_id: str, body: FrameSetFramingRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.set_framing(ctx, project_id, scene_id, body.framing))
        except service.FrameError as exc:
            raise fail(exc) from None

    @action("save-prompt")
    async def save_prompt(
        project_id: str, scene_id: str, body: FrameSavePromptRequest
    ) -> JSONResponse:
        try:
            out = service.save_prompt(ctx, project_id, scene_id, body.prompt, body.regenerate)
        except service.FrameError as exc:
            raise fail(exc) from None
        return JSONResponse(out)

    @action("continue-previous")
    async def continue_previous(
        project_id: str, scene_id: str, body: FrameContinueRequest
    ) -> JSONResponse:
        try:
            out = service.set_continue_previous(ctx, project_id, scene_id, body.enabled)
        except service.FrameError as exc:
            raise fail(exc) from None
        return JSONResponse(out)

    @action("upload", 201)
    async def upload(project_id: str, scene_id: str, file: UploadFile) -> JSONResponse:
        try:
            service.require(ctx, project_id, scene_id)
            data = await file.read(ctx.settings.max_upload_mb * 1024 * 1024 + 1)
            out = service.upload_frame(ctx, project_id, scene_id, data)
        except service.FrameError as exc:
            raise fail(exc) from None
        return JSONResponse(out, status_code=201)

    return router
