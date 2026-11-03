"""Voice routes: voice model, character voices and clip uploads."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from reelforge.adapters.mlx_audio import VOICE_MODELS
from reelforge.api.schemas import (
    VoiceClearOut,
    VoiceModelOut,
    VoiceModelPut,
    VoiceOut,
    VoiceSetRequest,
    VoicesOut,
)
from reelforge.context import AppContext
from reelforge.voice import service, slots


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["voice"])

    @router.get("/voice-model", response_model=VoiceModelOut)
    async def get_voice_model() -> JSONResponse:
        return JSONResponse(slots.voice_model_body(ctx))

    @router.put("/voice-model", response_model=VoiceModelOut)
    async def put_voice_model(body: VoiceModelPut) -> JSONResponse:
        if body.voice_model not in VOICE_MODELS:
            raise HTTPException(422, "voice_model must be one of: omnivoice, kokoro")
        slots.set_voice_model(ctx, body.voice_model)
        return JSONResponse(slots.voice_model_body(ctx))

    p = "/projects/{project_id}"

    def fail(exc: service.VoiceError) -> HTTPException:
        return HTTPException(exc.status, exc.message)

    @router.get(p + "/voices", response_model=VoicesOut)
    async def get_voices(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.voices_body(ctx, project_id))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @router.post(p + "/voices/characters/{key}:set", response_model=VoiceOut)
    async def set_voice(project_id: str, key: str, body: VoiceSetRequest) -> JSONResponse:
        try:
            out = service.set_character_voice(
                ctx,
                project_id,
                key,
                mode=body.mode,
                voice_id=body.voice_id,
                reference_text=body.reference_text,
                speed=body.speed,
            )
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(out)

    @router.post(p + "/voices/characters/{key}:clear", response_model=VoiceClearOut)
    async def clear_voice(project_id: str, key: str) -> JSONResponse:
        try:
            service.clear_character_voice(ctx, project_id, key)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse({"voice": None})

    @router.post(
        p + "/voices/characters/{key}:upload-reference", status_code=201, response_model=VoiceOut
    )
    async def upload_reference(
        project_id: str, key: str, file: UploadFile, reference_text: str | None = Form(None)
    ) -> JSONResponse:
        try:
            service.require(ctx, project_id, key)
            limit = ctx.settings.max_upload_mb * 1024 * 1024
            data = await file.read(limit + 1)
            clip = await service.screen_clip(ctx, data)
            try:
                out = service.store_reference(ctx, project_id, key, clip, reference_text)
            finally:
                clip.path.unlink(missing_ok=True)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(out, status_code=201)

    return router
