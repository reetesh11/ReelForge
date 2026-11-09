"""`gen_audio_cue` job: render one cue with the sound engine and fit it to the cue length."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec
from reelforge.artifacts.store import ArtifactSpec
from reelforge.audio import service
from reelforge.audio.backends import model_for, resolve_audio_adapter
from reelforge.audio.fit import FitError, fit_to_length
from reelforge.audio.state import OWNER_CUE, TAKE_KIND, AudioError, set_picked
from reelforge.cast import state as cast_state
from reelforge.db.models import Job

if TYPE_CHECKING:
    from reelforge.context import AppContext


async def audio_generate(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    project_id = job.project_id
    cue_id = str(job.payload.get("cue_id", ""))
    if project_id is None:
        raise AdapterError("gen_audio_cue needs a project")
    try:
        story = service.require(ctx, project_id)
        cue = service.find_cue(story, cue_id)
    except AudioError as exc:
        raise AdapterError(exc.message) from None
    if cue.kind == "silence":
        raise AdapterError(service.silence_text(cue_id))
    prompt = (cue.prompt or "").strip()
    if not prompt:
        raise AdapterError(service.empty_prompt_text(cue_id))
    span = service.cue_span(story, cue, service.timeline(ctx, project_id, story))
    length = span[1] - span[0] if span is not None else 0.0
    if length <= 0:
        raise AdapterError(f'Cue "{cue_id}" has no length.')

    started = time.monotonic()
    entry = model_for(ctx, cue.kind)
    take_no = len(service.cue_takes(ctx, project_id).get(cue_id, [])) + 1
    seed = cast_state.derive_seed(project_id, f"{cue_id}:audio:{take_no}:{job.id}")
    asked = min(length, entry.max_seconds) if entry.max_seconds else length
    task = TaskSpec(
        kind="audio",
        prompt=prompt,
        seed=seed,
        params={"duration_s": asked, "audio_kind": cue.kind},
        model=entry,
    )
    adapter = await resolve_audio_adapter(ctx)
    out_dir = ctx.settings.cache_tmp / job.id
    try:
        files = await adapter.run(task, out_dir, progress, cancel, ctx_job_id=job.id)
        if not files:
            raise AdapterError("the sound engine returned no audio")
        if cancel.cancelled:
            raise AdapterError("cancelled")
        fitted = out_dir / "fitted.wav"
        try:
            await fit_to_length(files[0].path, fitted, length, channels=1)
        except FitError as exc:
            raise AdapterError(str(exc)) from None
        take = ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=OWNER_CUE,
                owner_id=cue_id,
                kind=TAKE_KIND,
                subdir=f"audio/{cue_id}",
                prompt=prompt,
                seed=seed,
                model_key=entry.key,
                model_id=entry.id,
                model_revision=entry.revision,
                adapter=adapter.name,
                version=adapter.version,
                params={
                    "model_id": entry.id,
                    "audio_kind": cue.kind,
                    "requested_s": length,
                    "generated_s": asked,
                    "source": "generate",
                },
                job_id=job.id,
                duration_s=length,
                license=entry.license,
                license_url=entry.license_url,
            ),
            fitted,
            ext="wav",
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    set_picked(ctx, project_id, cue_id, take.id)
    ctx.queue.update_running(
        job.id,
        result={
            "cue_id": cue_id,
            "take_id": take.id,
            "take_no": take.take_no,
            "duration_s": length,
            "elapsed_s": round(time.monotonic() - started, 3),
        },
    )
