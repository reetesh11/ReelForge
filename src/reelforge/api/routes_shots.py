"""Shots routes: the shot board, render queue, takes, prompts and clip uploads."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from reelforge.api.routes_jobs import job_body
from reelforge.api.schemas import (
    JobOut,
    QueueMoveRequest,
    QueueOut,
    ShotActionOut,
    ShotSavePromptRequest,
    ShotSetQualityRequest,
    ShotSetTypeRequest,
    ShotsOut,
    ShotsRenderAllOut,
    ShotsRenderAllRequest,
    VoiceSelectTakeRequest,
)
from reelforge.context import AppContext
from reelforge.shots import service
from reelforge.shots.state import ShotError


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["shots"])

    def fail(exc: ShotError) -> HTTPException:
        return HTTPException(exc.status, exc.message)

    @router.get("/shots", response_model=ShotsOut)
    async def get_shots(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.shots_body(ctx, project_id))
        except ShotError as exc:
            raise fail(exc) from None

    @router.post("/shots:render-all", status_code=202, response_model=ShotsRenderAllOut)
    async def render_all(project_id: str, body: ShotsRenderAllRequest) -> JSONResponse:
        try:
            jobs, skipped = service.render_all(ctx, project_id, body.mode)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse({"jobs": [job_body(j) for j in jobs], "skipped": skipped}, 202)

    q = "/shots/queue"

    @router.post(q + ":move", response_model=QueueOut)
    async def queue_move(project_id: str, body: QueueMoveRequest) -> JSONResponse:
        try:
            return JSONResponse(service.move(ctx, project_id, body.job_id, body.direction))
        except ShotError as exc:
            raise fail(exc) from None

    @router.post(q + ":pause", response_model=QueueOut)
    async def queue_pause(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.set_paused(ctx, project_id, True))
        except ShotError as exc:
            raise fail(exc) from None

    @router.post(q + ":resume", response_model=QueueOut)
    async def queue_resume(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.set_paused(ctx, project_id, False))
        except ShotError as exc:
            raise fail(exc) from None

    @router.post(q + ":cancel", response_model=QueueOut)
    async def queue_cancel(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.cancel_queue(ctx, project_id))
        except ShotError as exc:
            raise fail(exc) from None

    sc = "/shots/{scene_id}"

    @router.post(sc + ":render", status_code=202, response_model=JobOut)
    async def render(project_id: str, scene_id: str) -> JSONResponse:
        try:
            job = service.render(ctx, project_id, scene_id)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    @router.post(sc + ":reroll", status_code=202, response_model=JobOut)
    async def reroll(project_id: str, scene_id: str) -> JSONResponse:
        try:
            job = service.render(ctx, project_id, scene_id, reroll=True)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    @router.post(sc + ":retry-draft", status_code=202, response_model=JobOut)
    async def retry_draft(project_id: str, scene_id: str) -> JSONResponse:
        try:
            job = service.retry_draft(ctx, project_id, scene_id)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    def action(name: str, status: int = 200):  # noqa: ANN202
        return router.post(f"{sc}:{name}", status_code=status, response_model=ShotActionOut)

    @action("approve")
    async def approve(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.approve(ctx, project_id, scene_id))
        except ShotError as exc:
            raise fail(exc) from None

    @action("select-take")
    async def select_take(
        project_id: str, scene_id: str, body: VoiceSelectTakeRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.select_take(ctx, project_id, scene_id, body.take_id))
        except ShotError as exc:
            raise fail(exc) from None

    @action("set-type")
    async def set_type(project_id: str, scene_id: str, body: ShotSetTypeRequest) -> JSONResponse:
        try:
            return JSONResponse(service.set_type(ctx, project_id, scene_id, body.shot_type))
        except ShotError as exc:
            raise fail(exc) from None

    @action("set-quality")
    async def set_quality(
        project_id: str, scene_id: str, body: ShotSetQualityRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.set_quality(ctx, project_id, scene_id, body.quality))
        except ShotError as exc:
            raise fail(exc) from None

    @action("save-prompt")
    async def save_prompt(
        project_id: str, scene_id: str, body: ShotSavePromptRequest
    ) -> JSONResponse:
        try:
            out = service.save_prompt(ctx, project_id, scene_id, body.prompt, body.rerender)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse(out)

    @action("dequeue")
    async def dequeue(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.dequeue(ctx, project_id, scene_id))
        except ShotError as exc:
            raise fail(exc) from None

    @action("upload-clip", 201)
    async def upload_clip(project_id: str, scene_id: str, file: UploadFile) -> JSONResponse:
        try:
            service.require(ctx, project_id, scene_id)
            data = await file.read(ctx.settings.max_clip_mb * 1024 * 1024 + 1)
            out = await service.upload_clip(ctx, project_id, scene_id, data)
        except ShotError as exc:
            raise fail(exc) from None
        return JSONResponse(out, status_code=201)

    return router
