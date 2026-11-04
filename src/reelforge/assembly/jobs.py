"""The `assemble_preview` and `assemble_final` job handlers."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.artifacts.store import ArtifactSpec
from reelforge.assembly.build import assembly_dir
from reelforge.assembly.edl import Edl, edl_hash, load_edl
from reelforge.assembly.render import RenderResult, render_edl
from reelforge.assembly.state import StepError
from reelforge.db.models import Artifact, Job

if TYPE_CHECKING:
    from reelforge.context import AppContext

PREVIEW_JOB = "assemble_preview"
FINAL_JOB = "assemble_final"
OWNER = "project"
ADAPTER = "ffmpeg"


def register_file(
    ctx: AppContext,
    project_id: str,
    kind: str,
    path: Path,
    *,
    job_id: str | None,
    inputs: list[str],
    params: dict[str, Any] | None = None,
    duration_s: float | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Artifact:
    """Make a rendered file an artifact so `/media/{id}` can serve it."""
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=OWNER,
        owner_id=project_id,
        kind=kind,
        subdir="assembly",
        prompt="",
        seed=0,
        model_key=ADAPTER,
        model_revision="",
        adapter=ADAPTER,
        version="1",
        params=params or {},
        input_artifact_ids=inputs,
        job_id=job_id,
        duration_s=duration_s,
        width=width,
        height=height,
    )
    return ctx.store.register_in_place(spec, path)


def source_ids(ctx: AppContext, edl: Edl) -> list[str]:
    """The artifacts an EDL is made of (ones that no longer exist are left out)."""
    wanted = list(
        dict.fromkeys([*(s.artifact for s in edl.video), *(d.artifact for d in edl.dialogue)])
    )
    with ctx.session_factory() as s:
        return [a for a in wanted if s.get(Artifact, a) is not None]


class StepTracker:
    """Remembers the step a render is in, so a failure can name it."""

    def __init__(self, progress: Callable[[int, str], None]) -> None:
        self.progress = progress
        self.step: str | None = None

    def __call__(self, pct: float, message: str) -> None:
        self.step = message.rsplit(" (", 1)[0]
        self.progress(int(pct), message)


def record_failure(ctx: AppContext, job_id: str, tracker: StepTracker, exc: Exception) -> None:
    step = exc.step if isinstance(exc, StepError) else tracker.step
    if step:
        ctx.queue.update_running(job_id, result={"failed_step": step})


def prune_previews(work: Path, keep: Path) -> None:
    for folder in work.glob("preview-*"):
        if folder != keep and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


async def assemble_preview(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    project_id = job.project_id
    if project_id is None:
        raise AdapterError("assemble_preview needs a project")
    digest = str(job.payload.get("edl_hash", ""))
    asm = assembly_dir(ctx, project_id)
    snap = asm / "edls" / f"{digest}.json"
    if not snap.is_file():
        raise AdapterError("The edit this preview was for is missing.")
    edl = load_edl(snap)
    work = asm / "work"
    out_dir = work / f"preview-{job.id}"
    tracker = StepTracker(progress)
    try:
        res: RenderResult = await render_edl(
            ctx, edl, out_dir, profile="preview", progress=tracker, cancel=cancel
        )
    except Exception as exc:
        record_failure(ctx, job.id, tracker, exc)
        raise
    inputs = source_ids(ctx, edl)
    preview = register_file(
        ctx, project_id, "preview", res.output, job_id=job.id, inputs=inputs,
        params={"edl_hash": digest}, duration_s=edl.total_duration_s, width=540, height=960,
    )  # fmt: skip
    graph = register_file(
        ctx, project_id, "filtergraph", res.filtergraph, job_id=job.id, inputs=[],
        params={"edl_hash": digest, "profile": "preview"},
    )  # fmt: skip
    prune_previews(work, out_dir)
    ctx.queue.update_running(
        job.id,
        result={
            "edl_hash": digest or edl_hash(edl),
            "artifact_id": preview.id,
            "filtergraph_artifact_id": graph.id,
            "captions_burned": res.captions_burned,
            "step_runs": res.step_runs,
        },
    )
