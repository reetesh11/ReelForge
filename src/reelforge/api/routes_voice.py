"""Voice routes: voice model, character voices and clip uploads."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from reelforge.adapters.mlx_audio import VOICE_MODELS
from reelforge.api.routes_jobs import job_body
from reelforge.api.schemas import (
    JobOut,
    VoiceClearOut,
    VoiceEditTextRequest,
    VoiceGenerateRequest,
    VoiceLineActionOut,
    VoiceModelOut,
    VoiceModelPut,
    VoiceOut,
    VoiceSelectTakeRequest,
    VoiceSetEmotionRequest,
    VoiceSetRequest,
    VoiceSettingsOut,
    VoiceSettingsPut,
    VoiceShortenOut,
    VoicesOut,
    VoiceTimingRequest,
)
from reelforge.context import AppContext
from reelforge.voice import service, slots
from reelforge.voice.mapping import MappingError


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

    @router.get(p + "/voices/settings", response_model=VoiceSettingsOut)
    async def get_voice_settings(project_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.settings_body(ctx, project_id))
        except service.VoiceError as exc:
            raise fail(exc) from None
        except MappingError as exc:
            raise HTTPException(500, str(exc)) from None

    @router.put(p + "/voices/settings", response_model=VoiceSettingsOut)
    async def put_voice_settings(project_id: str, body: VoiceSettingsPut) -> JSONResponse:
        try:
            return JSONResponse(service.set_phrase_gap(ctx, project_id, body.phrase_gap_ms))
        except service.VoiceError as exc:
            raise fail(exc) from None
        except MappingError as exc:
            raise HTTPException(500, str(exc)) from None

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

    @router.post(p + "/voices:generate", status_code=202, response_model=JobOut)
    async def generate(project_id: str, body: VoiceGenerateRequest) -> JSONResponse:
        try:
            job = service.enqueue_generation(ctx, project_id, body.mode, body.lines)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    @router.post(p + "/voices/presets/{preset_id}:preview", status_code=202, response_model=JobOut)
    async def preview_preset(project_id: str, preset_id: str) -> JSONResponse:
        try:
            job = service.enqueue_preset_preview(ctx, project_id, preset_id)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(job_body(job), status_code=202)

    ln = p + "/voices/lines/{scene_id}"

    def line_route(name: str, status: int = 200):  # noqa: ANN202
        return router.post(f"{ln}:{name}", status_code=status, response_model=VoiceLineActionOut)

    @line_route("select-take")
    async def select_take(
        project_id: str, scene_id: str, body: VoiceSelectTakeRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.select_take(ctx, project_id, scene_id, body.take_id))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @line_route("approve")
    async def approve_line(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.approve_line(ctx, project_id, scene_id))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @line_route("edit-text")
    async def edit_text(project_id: str, scene_id: str, body: VoiceEditTextRequest) -> JSONResponse:
        try:
            return JSONResponse(service.edit_text(ctx, project_id, scene_id, body.text))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @line_route("set-emotion")
    async def set_emotion(
        project_id: str, scene_id: str, body: VoiceSetEmotionRequest
    ) -> JSONResponse:
        try:
            return JSONResponse(service.set_emotion(ctx, project_id, scene_id, body.emotion))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @line_route("set-timing")
    async def set_timing(project_id: str, scene_id: str, body: VoiceTimingRequest) -> JSONResponse:
        try:
            out = service.set_timing(
                ctx,
                project_id,
                scene_id,
                speed=body.speed,
                pause_before=body.pause_before,
                pause_after=body.pause_after,
            )
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(out)

    @line_route("upload-recording", 201)
    async def upload_recording(project_id: str, scene_id: str, file: UploadFile) -> JSONResponse:
        try:
            service.require(ctx, project_id)
            data = await file.read(ctx.settings.max_upload_mb * 1024 * 1024 + 1)
            out = await service.upload_recording(ctx, project_id, scene_id, data)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return JSONResponse(out, status_code=201)

    @line_route("speed-up")
    async def speed_up(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.speed_up(ctx, project_id, scene_id))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @line_route("extend-scene")
    async def extend_scene(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse(service.extend_scene(ctx, project_id, scene_id))
        except service.VoiceError as exc:
            raise fail(exc) from None

    @router.post(f"{ln}:shorten", response_model=VoiceShortenOut)
    async def shorten(project_id: str, scene_id: str) -> JSONResponse:
        try:
            return JSONResponse({"proposal": await service.shorten(ctx, project_id, scene_id)})
        except service.VoiceError as exc:
            raise fail(exc) from None

    @router.get(p + "/voices/preview")
    async def preview(project_id: str, scene_id: str | None = None) -> Response:
        try:
            data, skipped = service.build_preview(ctx, project_id, scene_id)
        except service.VoiceError as exc:
            raise fail(exc) from None
        return Response(data, media_type="audio/wav", headers={"X-Skipped-Lines": str(skipped)})

    return router
