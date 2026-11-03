"""`gen_voice_take` job: render a batch of lines (or one preset preview) in one engine run."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.adapters.mlx_audio import (
    PRESETS,
    SPEED_MAX,
    SPEED_MIN,
    VOICE_MODELS,
    MlxAudioAdapter,
    VoiceLine,
    VoiceResult,
)
from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Job
from reelforge.voice import service, slots

if TYPE_CHECKING:
    from reelforge.context import AppContext

PREVIEW_TEXT = "नमस्ते, यह मेरी आवाज़ है।"
ENGINE = "mlx_audio"
ENGINE_VERSION = "tts_worker-1"


def _quiet(_pct: int, _message: str) -> None:
    """Adapter progress is dropped: the job message is always `line n of N`."""


def _model(ctx: AppContext) -> tuple[str, str, str, str]:
    """(voice model, models.toml key, model id, revision) of the model in use."""
    voice_model = slots.current_voice_model(ctx)
    key = VOICE_MODELS[voice_model]
    if key not in ctx.registry.keys():
        raise AdapterError(f"models.toml has no [{key}] entry")
    entry = ctx.registry.get(key)
    return voice_model, key, entry.id, entry.revision


def _adapter(ctx: AppContext) -> MlxAudioAdapter:
    s = ctx.settings
    return MlxAudioAdapter(s.mlx_audio_path, backend=s.backend, timeout_s=s.command_timeout_s)


def _effective_speed(voice_speed: float, line_speed: float) -> float:
    return round(min(SPEED_MAX, max(SPEED_MIN, voice_speed * line_speed)), 4)


async def voice_generate(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    if job.payload.get("preview"):
        await _preview(ctx, job, cancel)
        return
    project_id = job.project_id
    if project_id is None:
        raise AdapterError("gen_voice_take needs a project")
    scene_ids: list[str] = list(job.payload.get("scene_ids") or [])
    total = len(scene_ids)
    started = time.monotonic()
    voice_model, model_key, model_id, revision = _model(ctx)
    inputs = service.line_inputs(ctx, project_id)
    lines_result: dict[str, dict[str, Any]] = {}
    state = {"done": 0}

    def publish() -> None:
        ctx.queue.update_running(
            job.id,
            result={
                "scene_ids": scene_ids,
                "completed": state["done"],
                "total": total,
                "elapsed_s": round(time.monotonic() - started, 3),
                "lines": lines_result,
                "skipped": list(job.payload.get("skipped") or []),
            },
        )

    def finish(sid: str, outcome: dict[str, Any]) -> None:
        lines_result[sid] = outcome
        state["done"] += 1
        progress(round(100 * state["done"] / max(total, 1)), f"line {state['done']} of {total}")
        publish()

    publish()
    batch: list[VoiceLine] = []
    voices: dict[str, dict[str, Any]] = {}
    for sid in scene_ids:
        li = inputs.get(sid)
        slot = li.slot if li is not None else None
        if li is None or not li.text or not slots.voice_usable(slot) or slot is None:
            finish(sid, {"status": "failed", "error": "This line has no text or voice."})
            continue
        name = li.speaker_name or li.speaker or "this character"
        voice_name: str | None = None
        ref_audio: Path | None = None
        info: dict[str, Any] = {"mode": slot.mode, "model": voice_model}
        if slot.mode == "cloned":
            ref_id = slot.reference_artifact_id
            ref_path = _artifact_file(ctx, ref_id)
            if ref_path is None:
                msg = f"Reference clip for {name} is missing. Upload it again."
                finish(sid, {"status": "failed", "error": msg})
                continue
            ref_audio = ref_path
            info.update(reference_artifact_id=ref_id)
        elif slot.mode == "preset":
            preset = next((p for p in PRESETS[voice_model] if p.id == slot.voice_id), None)
            if preset is None:
                label = slots.MODEL_LABELS[voice_model]
                msg = f"{name}'s voice isn't available in {label}. Pick a voice again."
                finish(sid, {"status": "failed", "error": msg})
                continue
            voice_name = preset.voice
            info.update(voice_id=preset.id)
        else:
            finish(sid, {"status": "failed", "error": f"{name} uses recorded lines."})
            continue
        speed = _effective_speed(slot.speed, li.speed)
        voices[sid] = {"info": info, "speed": speed, "text": li.text}
        batch.append(
            VoiceLine(
                id=sid,
                text=li.text,
                voice=voice_name,
                ref_audio=ref_audio,
                ref_text=slot.reference_text if slot.mode == "cloned" else None,
                speed=speed,
            )
        )

    def on_line(result: VoiceResult) -> None:
        if result.error or result.path is None or result.duration_s is None:
            finish(result.id, {"status": "failed", "error": result.error or "No audio."})
            return
        meta = voices[result.id]
        ref = meta["info"].get("reference_artifact_id")
        take = service.write_take(
            ctx,
            project_id,
            result.id,
            result.path,
            duration_s=result.duration_s,
            text=meta["text"],
            speed=meta["speed"],
            voice=meta["info"],
            source="tts",
            model_key=model_key,
            model_id=model_id,
            revision=revision,
            adapter=ENGINE,
            version=ENGINE_VERSION,
            inputs=[ref] if ref else [],
            job_id=job.id,
        )
        finish(result.id, {"status": "done", "take_id": take.id})

    out_dir = ctx.settings.cache_tmp / job.id
    try:
        if batch:
            await _adapter(ctx).run_batch(
                batch, model_id, voice_model, out_dir, _quiet, cancel,
                on_line=on_line, job_id=job.id,
            )  # fmt: skip
        service.recompute_stage(ctx, project_id)
        failures = [v["error"] for v in lines_result.values() if v["status"] == "failed"]
        if total and len(failures) == total:
            raise AdapterError(failures[0])
    finally:
        publish()
        shutil.rmtree(out_dir, ignore_errors=True)


def _artifact_file(ctx: AppContext, artifact_id: str | None) -> Path | None:
    if artifact_id is None:
        return None
    from reelforge.db.models import Artifact  # noqa: PLC0415

    with ctx.session_factory() as s:
        art = s.get(Artifact, artifact_id)
    if art is None:
        return None
    path = ctx.store.absolute_path(art)
    return path if path.is_file() else None


async def _preview(ctx: AppContext, job: Job, cancel: CancelToken) -> None:
    project_id = job.project_id
    preset_id = str(job.payload.get("preview"))
    if project_id is None:
        raise AdapterError("gen_voice_take needs a project")
    voice_model, model_key, model_id, revision = _model(ctx)
    preset = next((p for p in PRESETS[voice_model] if p.id == preset_id), None)
    if preset is None:
        raise AdapterError("preset not found")
    out_dir = ctx.settings.cache_tmp / job.id
    line = VoiceLine(
        id="preview",
        text=PREVIEW_TEXT,
        voice=preset.voice,
        ref_audio=None,
        ref_text=None,
        speed=1.0,
    )
    try:
        results = await _adapter(ctx).run_batch(
            [line], model_id, voice_model, out_dir, _quiet, cancel, job_id=job.id
        )
        got = results[0]
        if got.error or got.path is None:
            raise AdapterError(got.error or "No audio.")
        spec = ArtifactSpec(
            project_id=project_id,
            owner_type="preset",
            owner_id=preset_id,
            kind="voice_preview",
            subdir="voices/previews",
            prompt=PREVIEW_TEXT,
            seed=0,
            model_key=model_key,
            model_id=model_id,
            model_revision=revision,
            adapter=ENGINE,
            version=ENGINE_VERSION,
            params={"preset": preset_id},
            job_id=job.id,
            duration_s=got.duration_s,
        )
        artifact = ctx.store.write(spec, got.path, ext="wav")
        ctx.queue.update_running(
            job.id, result={"audio_url": f"/media/{artifact.id}", "preset_id": preset_id}
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
