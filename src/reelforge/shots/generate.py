"""`gen_shot` job: render one shot from its start image (and voice take) with the video engine."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state as cast_state
from reelforge.db.models import Job
from reelforge.frames import service as frames_service
from reelforge.shots import prompts, service
from reelforge.shots.backends import resolve_video_adapter
from reelforge.shots.kinds import LAST_FRAME_KIND, OWNER_SCENE, SHOT_KIND
from reelforge.shots.media import NotAVideo, extract_last_frame
from reelforge.shots.state import FPS, SHOT_OOM_MESSAGE, get_slot, is_oom, update_slot

if TYPE_CHECKING:
    from reelforge.context import AppContext

MODEL_KEY = "video"


async def _motion_sentence(ctx: AppContext, f: service.SceneShot) -> str:
    """The LLM's one motion sentence; the action text itself when the LLM is down."""
    scene = f.scene
    try:
        raw = await ctx.llm.chat(
            prompts.motion_messages(
                action=scene.action, setting=scene.setting or "", shot_type=f.shot_type
            ),
            schema=prompts.motion_schema(),
        )
        parsed: Any = json.loads(raw)
        if isinstance(parsed, dict):
            text = str(parsed.get("motion_prompt") or "").strip()  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            if text:
                return " ".join(text.split())
    except Exception:  # noqa: BLE001, S110 - the action text is a fine fallback
        pass
    return scene.action


async def motion_text(ctx: AppContext, project_id: str, f: service.SceneShot) -> str:
    """The editable motion prompt: the user's text is kept, the LLM one is reused while its
    inputs are unchanged."""
    sid = f.scene.id
    slot = get_slot(ctx, project_id, sid)
    if slot is not None and slot.prompt_source == "user" and slot.motion_prompt.strip():
        return slot.motion_prompt
    basis_src = "\x1f".join([f.scene.action, f.scene.setting or "", f.shot_type])
    basis = hashlib.sha256(basis_src.encode()).hexdigest()[:32]
    if slot is not None and slot.motion_prompt.strip() and slot.prompt_basis == basis:
        return slot.motion_prompt
    text = await _motion_sentence(ctx, f)
    update_slot(ctx, project_id, sid, motion_prompt=text, prompt_source="llm", prompt_basis=basis)
    return text


async def shot_generate(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    project_id = job.project_id
    scene_id = str(job.payload.get("scene_id", ""))
    if project_id is None:
        raise AdapterError("gen_shot needs a project")
    story = service.voice_service.load_story(ctx, project_id)
    if story is None:
        raise AdapterError("There is no story yet.")
    f = service.shot_facts(ctx, project_id, story).get(scene_id)
    if f is None:
        raise AdapterError("scene not found")
    if f.blockers:
        raise AdapterError(service.BLOCKER_TEXT[f.blockers[0]])
    sources = service.task_inputs(f)
    input_ids = [a.id for a in sources]
    input_paths = [ctx.store.absolute_path(a) for a in sources]
    if not all(p.is_file() for p in input_paths):
        raise AdapterError("An input file for this shot is missing.")

    started = time.monotonic()
    facts = frames_service.scene_facts(ctx, project_id, story).get(scene_id)
    look = facts.master.look if facts is not None and facts.master is not None else ""
    motion = await motion_text(ctx, project_id, f)
    prompt = prompts.compose_motion_prompt(motion=motion, look=look, shot_type=f.shot_type)

    take_no = len(service.shot_takes(ctx, project_id).get(scene_id, [])) + 1
    seed = cast_state.derive_seed(project_id, f"{scene_id}:shot:{take_no}:{job.id}")
    entry = ctx.registry.get(MODEL_KEY)
    mode = "a2v" if f.shot_type == "talking" else "generate"
    params: dict[str, Any] = {
        "mode": mode,
        "frames": f.frames,
        "fps": FPS,
        "width": f.width,
        "height": f.height,
    }
    task = TaskSpec(
        kind="video",
        prompt=prompt,
        seed=seed,
        params=dict(params),
        model=entry,
        input_paths=input_paths,
    )
    adapter = await resolve_video_adapter(ctx)
    out_dir = ctx.settings.cache_tmp / job.id
    try:
        run_started = time.monotonic()
        try:
            files = await adapter.run(task, out_dir, progress, cancel, ctx_job_id=job.id)
        except AdapterError as exc:  # TransientError too: out of memory is never retried
            if is_oom(str(exc)):
                raise AdapterError(SHOT_OOM_MESSAGE) from exc
            raise
        render_s = round(time.monotonic() - run_started, 3)
        if not files:
            raise AdapterError("the video engine returned no video")
        if cancel.cancelled:
            raise AdapterError("cancelled")
        item = files[0]
        last_png = out_dir / "last.png"
        try:
            await extract_last_frame(item.path, last_png)
        except NotAVideo as exc:
            raise AdapterError(f"Couldn't read the rendered video: {exc}") from None
        audio = f.voice.id if f.shot_type == "talking" and f.voice is not None else None
        take = ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=OWNER_SCENE,
                owner_id=scene_id,
                kind=SHOT_KIND,
                subdir=f"shots/{scene_id}",
                prompt=prompt,
                seed=seed,
                model_key=entry.key,
                model_id=entry.id,
                model_revision=entry.revision,
                adapter=adapter.name,
                version=adapter.version,
                params={
                    **params,
                    "frame_id": f.image.id if f.image is not None else None,
                    "audio_id": audio,
                    "shot_type": f.shot_type,
                    "quality": f.quality,
                    "motion_prompt": motion,
                    "source": "render",
                    "inputs": input_ids,
                },
                input_artifact_ids=input_ids,
                job_id=job.id,
                width=f.width,
                height=f.height,
                duration_s=f.frames / FPS,
                license=entry.license,
                license_url=entry.license_url,
            ),
            item.path,
            ext="mp4",
        )
        last = ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=OWNER_SCENE,
                owner_id=scene_id,
                kind=LAST_FRAME_KIND,
                subdir=f"shots/{scene_id}/last",
                prompt="last frame of the shot",
                seed=seed,
                model_key=entry.key,
                model_id=entry.id,
                model_revision=entry.revision,
                adapter="ffmpeg",
                version="ffmpeg-1",
                params={"source": "ffmpeg", "inputs": [take.id]},
                input_artifact_ids=[take.id],
                job_id=job.id,
                width=f.width,
                height=f.height,
            ),
            last_png,
            ext="png",
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    update_slot(ctx, project_id, scene_id, approved_artifact_id=None)
    ctx.queue.update_running(
        job.id,
        result={
            "scene_id": scene_id,
            "take_id": take.id,
            "shot_type": f.shot_type,
            "quality": f.quality,
            "width": f.width,
            "height": f.height,
            "frames": f.frames,
            "render_s": render_s,
            "elapsed_s": round(time.monotonic() - started, 3),
            "inputs": input_ids,
            "last_frame_id": last.id,
        },
    )
    frames_service.recompute_stage(ctx, project_id)
