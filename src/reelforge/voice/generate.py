"""`gen_voice_take` job: render a batch of lines (or one preset preview) in one engine run."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.adapters.mlx_audio import (
    EDGE_PAD_S,
    PRESETS,
    VOICE_MODELS,
    MlxAudioAdapter,
    VoiceLine,
    VoiceResult,
)
from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Artifact, Job
from reelforge.voice import service, slots
from reelforge.voice.join import join_wavs
from reelforge.voice.mapping import MappingError
from reelforge.voice.plan import LinePlan, plan_line
from reelforge.voice.translit import needs_devanagari, to_devanagari

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
    try:
        mapping = service.current_mapping(ctx)
    except MappingError as exc:
        raise AdapterError(str(exc)) from None
    gap_ms = service.phrase_gap_ms(ctx, project_id, mapping)
    emotion_clips = slots.list_emotion_clips(ctx, project_id)
    batch: list[VoiceLine] = []
    runs: dict[str, _LineRun] = {}
    # Hindi voices read Devanagari; romanised Hinglish gives beeps or wrong sounds (see translit).
    convert = ctx.settings.llm_backend != "mock"
    converted_any = False
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
        speed = service.effective_speed(slot.speed, li.speed)
        clips = emotion_clips.get(li.speaker or "", {}) if slot.mode == "cloned" else {}
        plan = plan_line(
            li.raw_text,
            li.emotion,
            mapping=mapping,
            voice_model=voice_model,
            speed=speed,
            age=li.age,
            has_clip=clips.__contains__,
            gap_ms=gap_ms,
        )
        refs: list[tuple[Path | None, str | None, str | None]] = []
        broken: str | None = None
        for ph in plan.phrases:
            clip = clips.get(ph.emotion or "") if ph.reference == "emotion" else None
            if clip is None:
                refs.append(
                    (
                        ref_audio,
                        slot.reference_text if ref_audio else None,
                        info.get("reference_artifact_id"),
                    )
                )
                continue
            clip_path = _artifact_file(ctx, clip.artifact_id)
            if clip_path is None:
                broken = (
                    f"The {ph.emotion} reference clip for {name} is missing. "
                    "Upload it again or remove it."
                )
                break
            refs.append((clip_path, clip.transcript, clip.artifact_id))
        if broken is not None:
            finish(sid, {"status": "failed", "error": broken})
            continue
        used_clips = [
            (ph.emotion, ref[2])
            for ph, ref in zip(plan.phrases, refs, strict=True)
            if ph.reference == "emotion"
        ]
        if used_clips:
            info.update(reference_kind="emotion", emotion=used_clips[0][0])
        run = _LineRun(
            info=info,
            speed=speed,
            text=li.raw_text,
            plan=plan,
            reference_ids=[ref[2] for ref in refs],
            clip_ids=[str(cid) for _, cid in used_clips if cid],
        )
        runs[sid] = run
        many = len(plan.phrases) > 1
        for n, ph in enumerate(plan.phrases, start=1):
            phrase_audio, phrase_text, _ = refs[n - 1]
            spoken = ph.model_text
            if convert and needs_devanagari(spoken):
                spoken = await to_devanagari(ctx.llm, spoken)
                converted_any = True
            batch.append(
                VoiceLine(
                    id=f"{sid}#{n}" if many else sid,
                    text=spoken,
                    voice=voice_name,
                    ref_audio=phrase_audio,
                    ref_text=phrase_text if slot.mode == "cloned" else None,
                    speed=speed,
                    instruct=ph.instruct,
                    duration_scale=ph.duration_scale,
                    semitones=ph.post.semitones,
                    tempo=ph.post.tempo,
                    gain_db=ph.post.gain_db,
                    generation=ph.generation,
                    edge_pad_s=0.0 if many else EDGE_PAD_S,
                )
            )

    if converted_any:
        await ctx.ollama_unload()  # give the memory back before the voice model loads

    def on_line(result: VoiceResult) -> None:
        sid, _, number = result.id.partition("#")
        run = runs[sid]
        if run.closed:
            return
        if result.error or result.path is None or result.duration_s is None:
            run.closed = True
            finish(sid, {"status": "failed", "error": result.error or "No audio."})
            return
        run.results[int(number) if number else 1] = result
        if len(run.results) < len(run.plan.phrases):
            return
        run.closed = True
        try:
            take = _write_line_take(
                ctx, job, project_id, sid, run, out_dir, model_key, model_id, revision
            )
        except (ValueError, AdapterError) as exc:
            finish(sid, {"status": "failed", "error": str(exc)})
            return
        finish(sid, {"status": "done", "take_id": take.id})

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


@dataclass
class _LineRun:
    """One line being rendered: its plan and the phrase results that have arrived."""

    info: dict[str, Any]
    speed: float
    text: str
    plan: LinePlan
    reference_ids: list[str | None] = field(default_factory=lambda: [])
    clip_ids: list[str] = field(default_factory=lambda: [])
    results: dict[int, VoiceResult] = field(default_factory=lambda: {})
    closed: bool = False


def _write_line_take(
    ctx: AppContext,
    job: Job,
    project_id: str,
    sid: str,
    run: _LineRun,
    out_dir: Path,
    model_key: str,
    model_id: str,
    revision: str,
) -> Artifact:
    """Join the phrase audio (silence between phrases) and store it as the line's new take."""
    plan = run.plan
    ordered = [run.results[n] for n in range(1, len(plan.phrases) + 1)]
    if len(ordered) == 1 and ordered[0].path is not None and ordered[0].duration_s is not None:
        path, duration = ordered[0].path, ordered[0].duration_s
    else:
        paths = [r.path for r in ordered if r.path is not None]
        gap = (plan.gap_ms or 0) / 1000
        gaps = [gap + ph.post.pause_s for ph in plan.phrases[:-1]]
        path = out_dir / f"{sid}.joined.wav"
        duration = join_wavs(paths, gaps, path)
    extra: dict[str, Any] = {}
    requested = [r.duration_requested_s for r in ordered if r.duration_requested_s is not None]
    if requested:
        extra["duration_requested_s"] = round(sum(requested), 4)
    if plan.age_band is not None:
        extra["age_band"] = plan.age_band
    if plan.gap_ms is not None:
        extra["gap_ms"] = plan.gap_ms
    if plan.records_phrases:
        extra["phrases"] = [
            {
                **ph.recorded(),
                "duration_requested_s": r.duration_requested_s,
                "reference_artifact_id": ref_id,
            }
            for ph, r, ref_id in zip(plan.phrases, ordered, run.reference_ids, strict=True)
        ]
    ref = run.info.get("reference_artifact_id")
    return service.write_take(
        ctx,
        project_id,
        sid,
        path,
        duration_s=duration,
        text=run.text,
        speed=run.speed,
        voice=run.info,
        source="tts",
        model_key=model_key,
        model_id=model_id,
        revision=revision,
        adapter=ENGINE,
        version=ENGINE_VERSION,
        inputs=[*([ref] if ref else []), *run.clip_ids],
        job_id=job.id,
        extra_params=extra,
    )


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
