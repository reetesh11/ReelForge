"""The `AssemblyOut` body: EDL, takes, preview and export state, versions and warnings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.assembly import caption_step
from reelforge.assembly.build import (
    assembly_dir,
    blocked_reason,
    project_row,
    working_edl_path,
)
from reelforge.assembly.edl import CAPTION_PRESETS, Edl, edl_hash, load_edl
from reelforge.assembly.jobs import FINAL_JOB, PREVIEW_JOB
from reelforge.assembly.publish import collect_credits, licence_warnings
from reelforge.db.models import Artifact, Job, ReelVersion
from reelforge.shots import service as shots_service
from reelforge.voice import service as voice_service

if TYPE_CHECKING:
    from reelforge.context import AppContext

_STEP_RE = re.compile(r"^(?P<name>.*) \((?P<i>\d+) of (?P<n>\d+)\)$")


def version_dir(asm: Path, version: int) -> Path:
    return asm / f"v{version:03d}"


def parse_step(message: str | None) -> tuple[str | None, int | None, int | None]:
    if not message:
        return None, None, None
    m = _STEP_RE.match(message)
    if m is None:
        return message, None, None
    return m["name"], int(m["i"]), int(m["n"])


def _result(job: Job) -> dict[str, Any]:
    return dict(job.result or {})


def preview_state(
    ctx: AppContext, project_id: str, jobs: list[Job], current_hash: str | None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "state": "none",
        "step": None,
        "progress": None,
        "url": None,
        "job_id": None,
        "error": None,
        "rebuild_in_s": None,
    }
    previews = [j for j in jobs if j.type == PREVIEW_JOB and j.status != "cancelled"]
    done = next(
        (j for j in previews if j.status == "succeeded" and _result(j).get("artifact_id")), None
    )
    if done is not None:
        out["url"] = f"/media/{_result(done)['artifact_id']}"
    timer = ctx.previews.remaining(project_id)
    running = next((j for j in previews if j.status == "running"), None)
    queued = next((j for j in previews if j.status == "queued"), None)
    if timer is not None:
        out.update(state="pending", rebuild_in_s=round(timer, 3))
    elif running is not None:
        step, _, _ = parse_step(running.message)
        out.update(state="rebuilding", step=step, progress=running.progress, job_id=running.id)
    elif queued is not None:
        out.update(state="pending", job_id=queued.id)
    elif previews and previews[0].status == "failed":
        out.update(state="failed", job_id=previews[0].id, error=previews[0].error)
    elif done is not None and current_hash is not None:
        same = _result(done).get("edl_hash") == current_hash
        out["state"] = "up_to_date" if same else "out_of_date"
    elif current_hash is not None and previews:
        out["state"] = "out_of_date"
    if out["state"] == "pending" and timer is not None and running is not None:
        out["job_id"] = running.id
    return out


def export_state(jobs: list[Job]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "state": "idle",
        "step": None,
        "step_index": None,
        "step_total": None,
        "progress": None,
        "job_id": None,
        "failed_step": None,
        "error": None,
    }
    finals = [j for j in jobs if j.type == FINAL_JOB and j.status != "cancelled"]
    if not finals:
        return out
    latest = finals[0]
    if latest.status in ("queued", "running"):
        step, index, total = parse_step(latest.message if latest.status == "running" else None)
        out.update(
            state="running",
            step=step,
            step_index=index,
            step_total=total,
            progress=latest.progress,
            job_id=latest.id,
        )
    elif latest.status == "failed":
        out.update(
            state="failed",
            job_id=latest.id,
            failed_step=_result(latest).get("failed_step"),
            error=latest.error,
        )
    return out


def caption_status(ctx: AppContext, project_id: str, edl: Edl | None) -> dict[str, str]:
    """`words`, `line` or `pending` for every caption, from the alignment cache."""
    out: dict[str, str] = {}
    if edl is None:
        return out
    cache = caption_step.cache_dir(ctx, edl, assembly_dir(ctx, project_id) / "work")
    with ctx.session_factory() as s:
        for cap in edl.captions:
            clip = next((d for d in edl.dialogue if d.scene_id == cap.scene_id), None)
            take = s.get(Artifact, clip.artifact) if clip is not None else None
            if take is None or not cap.text.strip():
                out[cap.scene_id] = "line"
                continue
            words = caption_step.read_cache(
                cache / f"{caption_step.cache_key(ctx, take, cap.text)}.json"
            )
            out[cap.scene_id] = "pending" if words is None else ("words" if words else "line")
    return out


def versions(ctx: AppContext, project_id: str) -> list[dict[str, Any]]:
    asm = assembly_dir(ctx, project_id)
    with ctx.session_factory() as s:
        rows = list(
            s.scalars(
                select(ReelVersion)
                .where(ReelVersion.project_id == project_id)
                .order_by(ReelVersion.version)
            )
        )
        covers = {
            int((a.params or {}).get("version", 0)): a.id
            for a in s.scalars(
                select(Artifact).where(Artifact.project_id == project_id, Artifact.kind == "cover")
            )
        }
    out: list[dict[str, Any]] = []
    for row in rows:
        folder = version_dir(asm, row.version)
        cover = covers.get(row.version)
        out.append(
            {
                "version": row.version,
                "label": f"Reel v{row.version}",
                "reel_url": f"/media/{row.final_artifact_id}",
                "cover_url": f"/media/{cover}" if cover else "",
                "created_at": row.created_at.isoformat(),
                "missing": not (folder / "final.mp4").is_file()
                or not (folder / "edl.json").is_file(),
            }
        )
    return out


def shot_takes_out(ctx: AppContext, project_id: str) -> list[dict[str, Any]]:
    story = voice_service.load_story(ctx, project_id)
    if story is None:
        return []
    takes = shots_service.shot_takes(ctx, project_id)
    return [
        {
            "scene_id": scene.id,
            "takes": [
                {
                    "id": t.id,
                    "take_no": t.take_no,
                    "active": bool(t.is_active),
                    "video_url": f"/media/{t.id}",
                }
                for t in takes.get(scene.id, [])
            ],
        }
        for scene in story.scenes
    ]


def assembly_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    project = project_row(ctx, project_id)
    path = working_edl_path(ctx, project_id)
    edl = load_edl(path) if path.is_file() else None
    digest = edl_hash(edl) if edl is not None else None
    jobs = ctx.queue.list(project_id=project_id)
    warnings = licence_warnings(collect_credits(ctx, project_id, edl)) if edl is not None else []
    return {
        "stage": project.stage,
        "blocked_reason": blocked_reason(ctx, project_id),
        "edl": edl.model_dump(mode="json") if edl is not None else None,
        "edl_hash": digest,
        "shots": shot_takes_out(ctx, project_id),
        "caption_status": caption_status(ctx, project_id, edl),
        "preview": preview_state(ctx, project_id, jobs, digest),
        "export": export_state(jobs),
        "versions": versions(ctx, project_id),
        "licence_warnings": warnings,
        "caption_presets": [{"id": k, "label": v} for k, v in CAPTION_PRESETS.items()],
    }
