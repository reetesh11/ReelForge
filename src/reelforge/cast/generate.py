"""`cast.generate` job: candidate images for one story character, one image at a time."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import Adapter, AdapterError, CancelToken, TaskSpec
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state
from reelforge.cast.backends import resolve_image_adapter
from reelforge.cast.prompts import bible_messages, bible_schema, image_prompt
from reelforge.db.models import Artifact, CastSlot, Job
from reelforge.models_registry import ModelEntry

if TYPE_CHECKING:
    from reelforge.context import AppContext

REFINE_STRENGTH = 0.6
MODEL_KEY = "image"


async def ensure_bible_line(
    ctx: AppContext, project_id: str, slot: CastSlot | None, char: state.StoryCharacter, style: str
) -> CastSlot:
    """Keep the user's line; otherwise (re)write it from the story look with the LLM."""
    if (
        slot is not None
        and slot.bible_line.strip()
        and (slot.bible_source == "user" or slot.look_source == char.look)
    ):
        return slot
    line = ""
    try:
        raw = await ctx.llm.chat(
            bible_messages(char.name, char.look, style),
            schema=bible_schema(),
            heavy_next=True,
        )
        parsed: Any = json.loads(raw)
        if isinstance(parsed, dict):
            line = str(parsed.get("bible_line") or "").strip()  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except Exception:  # noqa: BLE001
        line = ""
    line = " ".join(line.split())
    source = "llm" if line else "raw"
    return state.update_slot(
        ctx,
        project_id,
        char.key,
        bible_line=line or char.look,
        bible_source=source,
        look_source=char.look,
    )


def _plan(job: Job, slot: CastSlot, project_id: str, key: str) -> tuple[list[int], dict[str, Any]]:
    """Seeds for this run plus the slot changes to reserve them."""
    payload = job.payload
    if payload.get("refine"):
        seed = slot.next_seed if slot.next_seed is not None else _base_seed(slot, project_id, key)
        return [seed], {"next_seed": seed + 1}
    if payload.get("regenerate") and slot.next_seed is not None:
        start = slot.next_seed
        count = state.CANDIDATES_PER_RUN
        return list(range(start, start + count)), {"next_seed": start + count}
    base = payload.get("seed")
    if base is None:
        base = _base_seed(slot, project_id, key)
    count = state.CANDIDATES_PER_RUN
    return list(range(base, base + count)), {
        "base_seed": base,
        "next_seed": base + count,
        "candidate_ids": [],
    }


def _base_seed(slot: CastSlot, project_id: str, key: str) -> int:
    return slot.base_seed if slot.base_seed is not None else state.derive_seed(project_id, key)


def _spec(
    ctx: AppContext,
    adapter: Adapter,
    entry: ModelEntry,
    *,
    project_id: str,
    key: str,
    kind: str,
    prompt: str,
    seed: int,
    params: dict[str, Any],
    inputs: list[str],
    job_id: str,
) -> ArtifactSpec:
    return ArtifactSpec(
        project_id=project_id,
        owner_type=state.OWNER_TYPE,
        owner_id=key,
        kind=kind,
        subdir=f"cast/{key}",
        prompt=prompt,
        seed=seed,
        model_key=entry.key,
        model_id=entry.id,
        model_revision=entry.revision,
        adapter=adapter.name,
        version=adapter.version,
        params=params,
        input_artifact_ids=inputs,
        job_id=job_id,
        license=entry.license,
        license_url=entry.license_url,
    )


def _quiet(_pct: int, _message: str) -> None:
    """Adapter progress is dropped: the job message is always `image n of N`."""


async def cast_generate(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    project_id = job.project_id
    key = str(job.payload.get("key", ""))
    if project_id is None:
        raise AdapterError("cast.generate needs a project")
    cast = state.load_story_cast(ctx, project_id)
    char = cast.characters.get(key)
    if char is None:
        raise AdapterError("character not found")
    slot = await ensure_bible_line(
        ctx, project_id, state.get_slot(ctx, project_id, key), char, cast.style
    )
    adapter = await resolve_image_adapter(ctx, job.payload.get("backend"))
    entry = ctx.registry.get(MODEL_KEY)

    refine: dict[str, Any] | None = job.payload.get("refine") or None
    previous: dict[str, Any] = dict(job.result or {})
    seeds: list[int] = list(previous.get("seeds") or [])
    if not seeds:
        seeds, reserve = _plan(job, slot, project_id, key)
        slot = state.update_slot(ctx, project_id, key, **reserve)
    total = len(seeds)
    source_path = None
    source_id = ""
    if refine:
        source_id = str(refine.get("from_candidate", ""))
        if source_id not in (slot.candidate_ids or []):
            raise AdapterError("candidate not found")
        with ctx.session_factory() as s:
            source = s.get(Artifact, source_id)
        if source is None:
            raise AdapterError("candidate not found")
        source_path = ctx.store.absolute_path(source)

    base_prompt = image_prompt(slot.bible_line, cast.style)
    started = time.monotonic()

    def publish(done: int) -> None:
        ids = list(state.get_slot(ctx, project_id, key).candidate_ids or [])  # type: ignore[union-attr]
        ctx.queue.update_running(
            job.id,
            result={
                "candidate_ids": ids,
                "completed": done,
                "total": total,
                "elapsed_s": round(time.monotonic() - started, 3),
                "seeds": seeds,
            },
        )

    for index, seed in enumerate(seeds):
        if cancel.cancelled:
            raise AdapterError("cancelled")
        progress(max(1, int(100 * index / total)), f"image {index + 1} of {total}")
        if refine:
            prompt = f"{base_prompt}. {str(refine.get('instruction', '')).strip()}".rstrip(". ")
            kind = f"{state.REFINE_PREFIX}{seed}"
            params: dict[str, Any] = {"strength": REFINE_STRENGTH}
            inputs = [source_id]
        else:
            prompt, kind, params, inputs = base_prompt, f"{state.GENERATED_PREFIX}{seed}", {}, []
        spec = _spec(
            ctx, adapter, entry, project_id=project_id, key=key, kind=kind, prompt=prompt,
            seed=seed, params=params, inputs=inputs, job_id=job.id,
        )  # fmt: skip
        hit = ctx.store.lookup(spec)
        if hit is None:
            out_dir = ctx.settings.cache_tmp / job.id / str(seed)
            task = TaskSpec(
                kind="image",
                prompt=prompt,
                seed=seed,
                params=params,
                model=entry,
                input_paths=[source_path] if source_path is not None else [],
            )
            try:
                files = await adapter.run(task, out_dir, _quiet, CancelToken(), ctx_job_id=job.id)
                if not files:
                    raise AdapterError("the image backend returned no image")
                item = files[0]
                hit = ctx.store.write(
                    spec.model_copy(update={"width": item.width, "height": item.height}),
                    item.path,
                    ext=item.ext,
                )
            finally:
                shutil.rmtree(out_dir, ignore_errors=True)
        current = state.get_slot(ctx, project_id, key)
        ids = list(current.candidate_ids or []) if current is not None else []
        if hit.id not in ids:
            ids.append(hit.id)
        state.update_slot(ctx, project_id, key, candidate_ids=ids)
        publish(index + 1)
    shutil.rmtree(ctx.settings.cache_tmp / job.id, ignore_errors=True)
