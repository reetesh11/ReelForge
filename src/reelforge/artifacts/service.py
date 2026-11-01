"""Artifact requests: cache lookup first, otherwise enqueue a generation job."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from reelforge.adapters.base import CancelToken, ProgressCb, TaskSpec
from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Artifact, Job

if TYPE_CHECKING:
    from reelforge.context import AppContext

DEFAULT_MODEL_KEY = {"image": "image", "video": "video", "audio": "tts"}


class ArtifactRequest(BaseModel):
    project_id: str
    owner_type: str
    owner_id: str
    kind: str
    media: Literal["image", "audio", "video"]
    prompt: str
    seed: int
    model_key: str | None = None
    params: dict[str, Any] = {}
    input_artifact_ids: list[str] = []
    subdir: str | None = None
    stage: Literal["story", "cast", "voices", "frames", "shots", "assembly"] | None = None
    heavy: bool = False
    mem_need_gb: float = 0.0


@dataclass
class RequestResult:
    cache_hit: bool
    artifact: Artifact | None
    job: Job | None


def build_spec(ctx: AppContext, req: ArtifactRequest, job_id: str | None = None) -> ArtifactSpec:
    entry = ctx.registry.get(req.model_key or DEFAULT_MODEL_KEY[req.media])
    return ArtifactSpec(
        project_id=req.project_id,
        owner_type=req.owner_type,
        owner_id=req.owner_id,
        kind=req.kind,
        subdir=req.subdir or f"{req.kind}s",
        prompt=req.prompt,
        seed=req.seed,
        model_key=entry.key,
        model_id=entry.id,
        model_revision=entry.revision,
        adapter=ctx.adapter.name,
        version=ctx.adapter.version,
        params=req.params,
        input_artifact_ids=req.input_artifact_ids,
        job_id=job_id,
    )


def request_artifact(ctx: AppContext, req: ArtifactRequest) -> RequestResult:
    hit = ctx.store.lookup(build_spec(ctx, req))
    if hit is not None:
        return RequestResult(cache_hit=True, artifact=hit, job=None)
    job = ctx.queue.enqueue(
        type="artifact.generate",
        project_id=req.project_id,
        payload=req.model_dump(),
        heavy=req.heavy,
        mem_need_gb=req.mem_need_gb,
    )
    return RequestResult(cache_hit=False, artifact=None, job=job)


async def generate_artifact(
    ctx: AppContext,
    job: Job,
    progress: ProgressCb,
    cancel: CancelToken,
) -> None:
    """Job handler for `artifact.generate`."""
    req = ArtifactRequest(**job.payload)
    spec = build_spec(ctx, req, job.id)
    if ctx.store.lookup(spec) is not None:
        return  # finished before a crash/restart: nothing to regenerate
    entry = ctx.registry.get(spec.model_key)
    inputs: list[Path] = []
    for aid in req.input_artifact_ids:
        with ctx.session_factory() as s:
            row = s.get(Artifact, aid)
        if row is not None:
            inputs.append(ctx.store.absolute_path(row))
    task = TaskSpec(
        kind=req.media,
        prompt=req.prompt,
        seed=req.seed,
        params=req.params,
        model=entry,
        input_paths=inputs,
    )
    out_dir = ctx.settings.cache_tmp / job.id
    try:
        produced = await ctx.adapter.run(task, out_dir, progress, cancel, ctx_job_id=job.id)
        for item in produced[:1]:
            final = spec.model_copy(
                update={"width": item.width, "height": item.height, "duration_s": item.duration_s}
            )
            ctx.store.write(final, item.path, ext=item.ext)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
