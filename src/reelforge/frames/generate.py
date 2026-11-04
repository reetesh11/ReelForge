"""`gen_frame` job: one key frame for one scene, drawn from the character's approved master."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state as cast_state
from reelforge.cast.backends import resolve_image_adapter
from reelforge.db.models import Artifact, Job
from reelforge.frames import prompts, service
from reelforge.frames.product import resolve_product
from reelforge.frames.state import (
    FRAME_HEIGHT,
    FRAME_KIND,
    FRAME_STRENGTH,
    FRAME_WIDTH,
    OWNER_SCENE,
    get_slot,
    update_slot,
)
from reelforge.story.schema import Story

if TYPE_CHECKING:
    from reelforge.context import AppContext

MODEL_KEY = "image"


def _quiet(_pct: int, _message: str) -> None:
    """Adapter progress is dropped: the job message is always `frame n of N`."""


async def _scene_sentence(ctx: AppContext, facts: service.SceneFacts) -> str:
    """The LLM's one sentence for the scene; the action text itself when the LLM is down."""
    scene = facts.scene
    try:
        raw = await ctx.llm.chat(
            prompts.scene_messages(
                action=scene.action, setting=scene.setting or "", line=scene.line or ""
            ),
            schema=prompts.scene_schema(),
        )
        parsed: Any = json.loads(raw)
        if isinstance(parsed, dict):
            text = str(parsed.get("scene_sentence") or "").strip()  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            if text:
                return " ".join(text.split())
    except Exception:  # noqa: BLE001, S110 - the action text is a fine fallback
        pass
    return scene.action


async def frame_prompt(
    ctx: AppContext, project_id: str, story: Story, facts: service.SceneFacts, product: bool
) -> tuple[str, str]:
    """(prompt, source). A prompt the user wrote is kept; the LLM one is reused while its
    inputs are unchanged."""
    scene_id = facts.scene.id
    slot = get_slot(ctx, project_id, scene_id)
    if slot is not None and slot.prompt_source == "user" and slot.prompt.strip():
        return slot.prompt, "user"
    basis = service.prompt_basis(story, facts, product)
    if slot is not None and slot.prompt.strip() and slot.prompt_basis == basis:
        return slot.prompt, "llm"
    sentence = await _scene_sentence(ctx, facts)
    prompt = service.default_prompt(story, facts, product, sentence)
    update_slot(ctx, project_id, scene_id, prompt=prompt, prompt_source="llm", prompt_basis=basis)
    return prompt, "llm"


async def frame_generate(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    project_id = job.project_id
    scene_id = str(job.payload.get("scene_id", ""))
    if project_id is None:
        raise AdapterError("gen_frame needs a project")
    story = service.voice_service.load_story(ctx, project_id)
    if story is None:
        raise AdapterError("There is no story yet.")
    facts = service.scene_facts(ctx, project_id, story).get(scene_id)
    if facts is None:
        raise AdapterError("scene not found")
    master = facts.master
    if master is None:
        raise AdapterError("There is no character in this scene.")
    if master.artifact_id is None:
        raise AdapterError(f"Approve a master for {master.name} in Cast first")
    with ctx.session_factory() as s:
        master_art = s.get(Artifact, master.artifact_id)
    master_path = ctx.store.absolute_path(master_art) if master_art is not None else None
    if master_path is None or not master_path.is_file():
        raise AdapterError(f"The master for {master.name} is missing. Approve it again in Cast.")

    started = time.monotonic()
    progress(1, f"frame {job.payload.get('index', 1)} of {job.payload.get('total', 1)}")
    pack = None
    if facts.scene.product_in_shot and story.product is not None:
        pack = resolve_product(ctx, project_id, story)
    prompt, source = await frame_prompt(ctx, project_id, story, facts, pack is not None)
    input_ids = [master.artifact_id] + ([pack.id] if pack is not None else [])
    input_paths = [master_path] + ([ctx.store.absolute_path(pack)] if pack is not None else [])

    take_no = len(service.frame_takes(ctx, project_id).get(scene_id, [])) + 1
    seed = cast_state.derive_seed(project_id, f"{scene_id}:frame:{take_no}:{job.id}")
    entry = ctx.registry.get(MODEL_KEY)
    adapter = await resolve_image_adapter(ctx)
    params: dict[str, Any] = {
        "strength": FRAME_STRENGTH,
        "width": FRAME_WIDTH,
        "height": FRAME_HEIGHT,
    }
    task = TaskSpec(
        kind="image",
        prompt=prompt,
        seed=seed,
        params=dict(params),
        model=entry,
        input_paths=input_paths,
    )
    out_dir = ctx.settings.cache_tmp / job.id
    try:
        files = await adapter.run(task, out_dir, _quiet, cancel, ctx_job_id=job.id)
        if not files:
            raise AdapterError("the image backend returned no image")
        item = files[0]
        if cancel.cancelled:
            raise AdapterError("cancelled")
        spec = ArtifactSpec(
            project_id=project_id,
            owner_type=OWNER_SCENE,
            owner_id=scene_id,
            kind=FRAME_KIND,
            subdir=f"frames/{scene_id}",
            prompt=prompt,
            seed=seed,
            model_key=entry.key,
            model_id=entry.id,
            model_revision=entry.revision,
            adapter=adapter.name,
            version=adapter.version,
            params={
                **params,
                "framing": facts.framing,
                "look": master.look,
                "master_id": master.artifact_id,
                "prompt_source": source,
                "source": "render",
                "inputs": input_ids,
            },
            input_artifact_ids=input_ids,
            job_id=job.id,
            width=item.width,
            height=item.height,
            license=entry.license,
            license_url=entry.license_url,
        )
        take = ctx.store.write(spec, item.path, ext=item.ext)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    service.clear_approval(ctx, project_id, scene_id)
    ctx.queue.update_running(
        job.id,
        result={
            "scene_id": scene_id,
            "take_id": take.id,
            "inputs": input_ids,
            "elapsed_s": round(time.monotonic() - started, 3),
        },
    )
    service.recompute_stage(ctx, project_id)
