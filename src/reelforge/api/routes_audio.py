"""Sound routes: the cue list, cue edits, takes, uploads, mix settings and the full-mix preview."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from reelforge.api.schemas import (
    AudioMoveRequest,
    AudioOut,
    AudioSettingsOut,
    AudioSettingsRequest,
    VoiceSelectTakeRequest,
)
from reelforge.audio import service
from reelforge.audio.state import AudioError
from reelforge.context import AppContext
from reelforge.story.schema import Cue


def fail(exc: AudioError) -> HTTPException | JSONResponse:
    if exc.errors is not None:
        return JSONResponse({"detail": exc.message, "errors": exc.errors}, status_code=exc.status)
    return HTTPException(exc.status, exc.message)


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["audio"])

    def respond(call: Callable[[], Mapping[str, Any]], status: int = 200) -> JSONResponse:
        try:
            return JSONResponse(call(), status_code=status)
        except AudioError as exc:
            out = fail(exc)
            if isinstance(out, HTTPException):
                raise out from None
            return out

    @router.get("/audio", response_model=AudioOut)
    async def get_audio(project_id: str) -> JSONResponse:
        return respond(lambda: service.audio_body(ctx, project_id))

    @router.get("/audio/settings", response_model=AudioSettingsOut)
    async def get_settings(project_id: str) -> JSONResponse:
        return respond(lambda: service.settings_body(ctx, project_id))

    @router.put("/audio/settings", response_model=AudioSettingsOut)
    async def put_settings(project_id: str, body: AudioSettingsRequest) -> JSONResponse:
        values = {k: v for k, v in body.model_dump().items() if v is not None}
        return respond(lambda: service.update_settings(ctx, project_id, **values))

    @router.post("/audio/cues", status_code=201, response_model=AudioOut)
    async def add_cue(project_id: str, body: Cue) -> JSONResponse:
        return respond(lambda: service.add_cue(ctx, project_id, body), 201)

    @router.put("/audio/cues/{cue_id}", response_model=AudioOut)
    async def put_cue(project_id: str, cue_id: str, body: Cue) -> JSONResponse:
        return respond(lambda: service.update_cue(ctx, project_id, cue_id, body))

    @router.delete("/audio/cues/{cue_id}", response_model=AudioOut)
    async def delete_cue(project_id: str, cue_id: str) -> JSONResponse:
        return respond(lambda: service.delete_cue(ctx, project_id, cue_id))

    @router.post("/audio/cues:approve-all", response_model=AudioOut)
    async def approve_all(project_id: str) -> JSONResponse:
        return respond(lambda: service.approve_all(ctx, project_id))

    @router.post("/audio/cues/{cue_id}:move", response_model=AudioOut)
    async def move_cue(project_id: str, cue_id: str, body: AudioMoveRequest) -> JSONResponse:
        return respond(lambda: service.move_cue(ctx, project_id, cue_id, body.direction))

    @router.post("/audio/cues/{cue_id}:approve", response_model=AudioOut)
    async def approve_cue(project_id: str, cue_id: str) -> JSONResponse:
        return respond(lambda: service.approve_cue(ctx, project_id, cue_id))

    @router.post("/audio/cues/{cue_id}:dismiss", response_model=AudioOut)
    async def dismiss_cue(project_id: str, cue_id: str) -> JSONResponse:
        return respond(lambda: service.dismiss_cue(ctx, project_id, cue_id))

    @router.post("/audio/cues/{cue_id}:select-take", response_model=AudioOut)
    async def select_take(
        project_id: str, cue_id: str, body: VoiceSelectTakeRequest
    ) -> JSONResponse:
        return respond(lambda: service.select_take(ctx, project_id, cue_id, body.take_id))

    return router
