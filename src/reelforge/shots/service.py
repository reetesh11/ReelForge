"""Shots stage operations: scene facts, blockers and staleness, then the board and actions."""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Artifact, Job, Project, ShotSlot
from reelforge.frames import service as frames_service
from reelforge.ids import new_id
from reelforge.jobs.queue import JobNotFound, JobStateError
from reelforge.shots import kinds
from reelforge.shots import state as shot_state
from reelforge.shots.backends import ENGINE_DOWN, engine_status
from reelforge.shots.media import NotAVideo, extract_last_frame
from reelforge.shots.state import (
    SHOT_JOB,
    ShotError,
    effective_quality,
    get_slot,
    list_slots,
    size_for,
    update_slot,
)
from reelforge.shots.uploads import NOT_VIDEO, screen_clip
from reelforge.story.schema import Scene, Story
from reelforge.story.staleness import ChangeRow, is_stale
from reelforge.voice import service as voice_service
from reelforge.voice.frames import frames_for

if TYPE_CHECKING:
    from reelforge.context import AppContext

SHOTS_LOCKED = "Approve the key frames first."
BLOCKER_TEXT = {
    "frame_not_approved": "Approve the key frame first.",
    "voice_not_approved": "Approve the voice take first.",
    "waiting_previous": "Waiting for the previous shot.",
}
FALLBACK_SCENE_S = 3.0


def require(ctx: AppContext, project_id: str, scene_id: str | None = None) -> Story:
    """Project exists, key frames approved, and `scene_id` (when given) is a scene."""
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None:
        raise ShotError(404, "project not found")
    if not frames_service.stage_at_least(project.stage, "FRAMES_APPROVED"):
        raise ShotError(409, SHOTS_LOCKED)
    story = voice_service.load_story(ctx, project_id)
    if story is None:
        raise ShotError(409, SHOTS_LOCKED)
    if scene_id is not None and scene_id not in {s.id for s in story.scenes}:
        raise ShotError(404, "scene not found")
    return story


@dataclass(frozen=True)
class SceneShot:
    scene: Scene
    position: int
    slot: ShotSlot | None
    auto_type: str
    shot_type: str
    quality: str
    width: int
    height: int
    frames: int
    voice: Artifact | None
    image: Artifact | None
    blockers: list[str]
    frame_card: dict[str, Any]


def shot_facts(
    ctx: AppContext, project_id: str, story: Story, frame_cards: list[dict[str, Any]] | None = None
) -> dict[str, SceneShot]:
    cards = {
        f["scene_id"]: f
        for f in (
            frame_cards if frame_cards is not None else frames_service.build_frames(ctx, project_id)
        )
    }
    inputs = voice_service.line_inputs(ctx, project_id)
    voice_takes = voice_service.takes_by_scene(ctx, project_id)
    slots = list_slots(ctx, project_id)
    frame_takes = frames_service.frame_takes(ctx, project_id)
    out: dict[str, SceneShot] = {}
    for position, scene in enumerate(story.scenes, start=1):
        sid = scene.id
        li = inputs.get(sid)
        slot = slots.get(sid)
        voice = next((t for t in voice_takes.get(sid, []) if t.is_active), None)
        voice_ok = voice is not None and li is not None and li.approved_artifact_id == voice.id
        auto = "talking" if voice_ok else ("continue" if scene.continue_from else "action")
        kind = (
            slot.shot_type if slot is not None and slot.shot_type in shot_state.SHOT_TYPES else auto
        )
        quality = effective_quality(ctx.settings, slot)
        width, height = size_for(ctx.settings, quality)
        frames = (
            li.scene_frames
            if li is not None and li.scene_frames is not None
            else frames_for(scene.duration or FALLBACK_SCENE_S)
        )
        card = cards.get(sid, {})
        continuing = bool(card.get("continue_previous"))
        blockers: list[str] = []
        image: Artifact | None
        if kind == "continue" or continuing:
            image = frames_service.previous_last_frame(ctx, project_id, story, sid)
            if image is None:
                blockers.append("waiting_previous")
        else:
            image = next((t for t in frame_takes.get(sid, []) if t.is_active), None)
            if card.get("state") != "approved":
                blockers.append("frame_not_approved")
        if kind == "talking" and not voice_ok:
            blockers.append("voice_not_approved")
        out[sid] = SceneShot(
            scene=scene,
            position=position,
            slot=slot,
            auto_type=auto,
            shot_type=kind,
            quality=quality,
            width=width,
            height=height,
            frames=frames,
            voice=voice,
            image=image,
            blockers=blockers,
            frame_card=card,
        )
    return out


def task_inputs(f: SceneShot) -> list[Artifact]:
    """The artifacts a render reads: the start image, plus the voice take for a talking shot."""
    items: list[Artifact] = []
    if f.image is not None:
        items.append(f.image)
    if f.shot_type == "talking" and f.voice is not None:
        items.append(f.voice)
    return items


def take_stale(take: Artifact, changes: list[ChangeRow], f: SceneShot) -> bool:
    if is_stale(kinds.SHOT_KIND, frames_service.aware(take.created_at), changes):
        return True
    params: dict[str, Any] = take.params or {}
    if params.get("source") == "upload":
        return False
    if f.image is not None and params.get("frame_id") != f.image.id:
        return True
    if f.shot_type == "talking":
        audio = f.voice.id if f.voice is not None else None
        if params.get("audio_id") != audio:
            return True
    return (
        params.get("frames") != f.frames
        or params.get("shot_type") != f.shot_type
        or params.get("quality") != f.quality
    )


def shot_takes(ctx: AppContext, project_id: str) -> dict[str, list[Artifact]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.owner_type == kinds.OWNER_SCENE,
                Artifact.kind == kinds.SHOT_KIND,
            )
            .order_by(Artifact.take_no)
        )
        out: dict[str, list[Artifact]] = {}
        for r in rows:
            out.setdefault(r.owner_id, []).append(r)
    return out


def shot_jobs(ctx: AppContext, project_id: str) -> list[Any]:
    return frames_service.jobs_of(ctx, project_id, SHOT_JOB)


# ---- the board -----------------------------------------------------------------------------


def _take_out(
    ctx: AppContext, t: Artifact, stale: bool, approved_id: str | None, quality: str
) -> dict[str, Any]:
    params: dict[str, Any] = t.params or {}
    last = kinds.last_frame_for_take(ctx, t.id)
    return {
        "id": t.id,
        "take_no": t.take_no,
        "seed": t.seed,
        "active": t.is_active,
        "approved": t.id == approved_id,
        "stale": stale,
        "source": "upload" if params.get("source") == "upload" else "render",
        "quality": str(params.get("quality") or quality),
        "video_url": f"/media/{t.id}",
        "last_frame_id": last.id if last is not None else None,
        "inputs": list(params.get("inputs") or []),
    }


def build_shots(
    ctx: AppContext, project_id: str, frame_cards: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

    story = voice_service.load_story(ctx, project_id)
    if story is None:
        return []
    facts = shot_facts(ctx, project_id, story, frame_cards)
    takes = shot_takes(ctx, project_id)
    changes = frames_service.changes_by_scene(ctx, project_id)
    jobs = shot_jobs(ctx, project_id)
    out: list[dict[str, Any]] = []
    for sid, f in facts.items():
        scene_takes = takes.get(sid, [])
        active = next((t for t in scene_takes if t.is_active), None)
        approved_id = f.slot.approved_artifact_id if f.slot is not None else None
        stale_by_id = {t.id: take_stale(t, changes.get(sid, []), f) for t in scene_takes}
        job_s, job_message = frames_service.job_state(jobs, sid, active)
        message: str | None = None
        if job_s in ("queued", "rendering"):
            state = job_s or "queued"
        elif job_s == "failed":
            state, message = "failed", job_message
        elif active is None:
            state = "no_shot"
        elif stale_by_id[active.id]:
            state = "stale"
        elif approved_id == active.id:
            state = "approved"
        else:
            state = "ready"
        mine = [j for j in jobs if j.payload.get("scene_id") == sid]
        running_here = [j for j in mine if j.status in ("queued", "running")]
        card: dict[str, Any] = {
            "scene_id": sid,
            "position": f.position,
            "shot_type": f.shot_type,
            "shot_type_auto": f.auto_type,
            "quality": f.quality,
            "width": f.width,
            "height": f.height,
            "frames": f.frames,
            "shot_length_s": f.frames / shot_state.FPS,
            "motion_prompt": f.slot.motion_prompt if f.slot is not None else "",
            "state": state,
            "blockers": list(f.blockers),
            "frame_url": f"/media/{f.image.id}" if f.image is not None else None,
            "takes": [
                _take_out(ctx, t, stale_by_id[t.id], approved_id, f.quality) for t in scene_takes
            ],
            "job": job_body(running_here[0]) if running_here else None,
        }
        if message:
            card["message"] = message
        if state == "failed" and message == shot_state.SHOT_OOM_MESSAGE:
            card["oom"] = True
            if f.quality != "draft":
                card["can_retry_draft"] = True
        out.append(card)
    return out


def counts(shots: list[dict[str, Any]]) -> tuple[int, int, int]:
    return (
        sum(1 for s in shots if s["state"] == "approved"),
        len(shots),
        sum(1 for s in shots if s["state"] == "stale"),
    )


def shots_complete(ctx: AppContext, project_id: str) -> bool:
    shots = build_shots(ctx, project_id)
    return bool(shots) and all(s["state"] == "approved" for s in shots)


# ---- the render queue ----------------------------------------------------------------------


def render_history(ctx: AppContext) -> dict[tuple[str, int, int], float]:
    """Mean recorded render time by (shot type, width, height) over succeeded shot jobs."""
    times: dict[tuple[str, int, int], list[float]] = {}
    for job in ctx.queue.list(status="succeeded"):
        res: dict[str, Any] = job.result or {}
        if job.type != SHOT_JOB or "render_s" not in res:
            continue
        key = (str(res.get("shot_type")), int(res.get("width", 0)), int(res.get("height", 0)))
        times.setdefault(key, []).append(float(res["render_s"]))
    return {k: sum(v) / len(v) for k, v in times.items()}


def estimate_s(
    history: dict[tuple[str, int, int], float], shot_type: str, quality: str, w: int, h: int
) -> int:
    mean = history.get((shot_type, w, h))
    if mean is not None:
        return max(1, round(mean))
    return shot_state.DEFAULT_ESTIMATE_S[(shot_type, quality)]


def minutes_text(seconds: float) -> str:
    return f"about {max(1, math.ceil(seconds / 60))} min"


def queue_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    active = [j for j in shot_jobs(ctx, project_id) if j.status in ("queued", "running")]
    active.sort(
        key=lambda j: (j.status != "running", -j.priority, frames_service.aware(j.created_at), j.id)
    )
    history = render_history(ctx)
    rows: list[dict[str, Any]] = []
    running: dict[str, Any] | None = None
    for position, job in enumerate(active, start=1):
        payload = job.payload
        shot_type = str(payload.get("shot_type", "action"))
        quality = str(payload.get("quality", "draft"))
        w, h = size_for(ctx.settings, quality)
        est = estimate_s(history, shot_type, quality, w, h)
        sid = str(payload.get("scene_id", ""))
        rows.append(
            {
                "job_id": job.id,
                "scene_id": sid,
                "position": position,
                "shot_type": shot_type,
                "quality": quality,
                "width": w,
                "height": h,
                "status": job.status,
                "estimate_s": est,
                "estimate_text": minutes_text(est),
                "can_move": job.status == "queued",
            }
        )
        if job.status == "running" and running is None:
            started = job.started_at
            elapsed = (
                max(0, int((datetime.now(UTC) - frames_service.aware(started)).total_seconds()))
                if started is not None
                else 0
            )
            running = {
                "scene_id": sid,
                "index": int(payload.get("index", 1)),
                "total": int(payload.get("total", 1)),
                "elapsed_s": elapsed,
            }
    total_s = sum(r["estimate_s"] for r in rows)
    n = len(rows)
    noun = "shot" if n == 1 else "shots"
    paused = project_id in ctx.worker.paused_projects
    return {
        "paused": paused,
        "rows": rows,
        "total_shots": n,
        "total_s": total_s,
        "total_text": f"{n} {noun} - {minutes_text(total_s)} - keep the Mac plugged in",
        "running": running,
    }


def _queued_rows(ctx: AppContext, project_id: str) -> list[Any]:
    jobs = [j for j in shot_jobs(ctx, project_id) if j.status == "queued"]
    jobs.sort(key=lambda j: (-j.priority, frames_service.aware(j.created_at), j.id))
    return jobs


def move(ctx: AppContext, project_id: str, job_id: str, direction: str) -> dict[str, Any]:
    require(ctx, project_id)
    if direction not in ("up", "down"):
        raise ShotError(422, "direction must be up or down")
    try:
        job = ctx.queue.get(job_id)
    except JobNotFound:
        raise ShotError(404, "job not found") from None
    if job.project_id != project_id or job.type != SHOT_JOB:
        raise ShotError(404, "job not found")
    if job.status != "queued":
        raise ShotError(409, "That shot has already started.")
    queued = _queued_rows(ctx, project_id)
    ids = [j.id for j in queued]
    i = ids.index(job_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        for rank, jid in enumerate(ids):
            ctx.queue.transition(jid, "queued", priority=len(ids) - rank)
    return queue_body(ctx, project_id)


def set_paused(ctx: AppContext, project_id: str, paused: bool) -> dict[str, Any]:
    require(ctx, project_id)
    if paused:
        ctx.worker.paused_projects.add(project_id)
    else:
        ctx.worker.paused_projects.discard(project_id)
    return queue_body(ctx, project_id)


def cancel_queue(ctx: AppContext, project_id: str) -> dict[str, Any]:
    require(ctx, project_id)
    jobs = [j for j in shot_jobs(ctx, project_id) if j.status in ("queued", "running")]
    jobs.sort(key=lambda j: j.status != "queued")
    for job in jobs:
        with contextlib.suppress(JobStateError):
            ctx.queue.cancel(job.id)
    frames_service.recompute_stage(ctx, project_id)
    return queue_body(ctx, project_id)


def dequeue(ctx: AppContext, project_id: str, scene_id: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    mine = [j for j in shot_jobs(ctx, project_id) if j.payload.get("scene_id") == scene_id]
    mine = [j for j in mine if j.status in ("queued", "running")]
    if not mine:
        raise ShotError(404, "That shot is not in the queue.")
    if mine[0].status == "running":
        raise ShotError(409, "That shot has already started.")
    with contextlib.suppress(JobStateError):
        ctx.queue.cancel(mine[0].id)
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)


# ---- requests ------------------------------------------------------------------------------


def shots_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    require(ctx, project_id)
    shots = build_shots(ctx, project_id)
    approved, total, stale = counts(shots)
    ok, message = engine_status(ctx)
    return {
        "stage": voice_service.project_stage(ctx, project_id),
        "engine": {"ok": ok, "message": message},
        "approved_count": approved,
        "total": total,
        "stale_count": stale,
        "shots": shots,
        "queue": queue_body(ctx, project_id),
    }


def shot_response(ctx: AppContext, project_id: str, scene_id: str, **extra: Any) -> dict[str, Any]:
    shots = build_shots(ctx, project_id)
    approved, total, _ = counts(shots)
    card = next(s for s in shots if s["scene_id"] == scene_id)
    return {
        "project_stage": voice_service.project_stage(ctx, project_id),
        "approved_count": approved,
        "total": total,
        "shot": card,
        **extra,
    }


def _check_engine(ctx: AppContext) -> None:
    ok, message = engine_status(ctx)
    if not ok:
        raise ShotError(409, message or ENGINE_DOWN)


def _enqueue(
    ctx: AppContext, project_id: str, f: SceneShot, batch_id: str, index: int, total: int
) -> Job:
    return ctx.queue.enqueue(
        type=SHOT_JOB,
        project_id=project_id,
        payload={
            "stage": "shots",
            "scene_id": f.scene.id,
            "shot_type": f.shot_type,
            "quality": f.quality,
            "batch_id": batch_id,
            "index": index,
            "total": total,
        },
        heavy=True,
        mem_need_gb=ctx.settings.shot_mem_gb,
    )


def _active_job(ctx: AppContext, project_id: str, scene_id: str) -> Job | None:
    for job in shot_jobs(ctx, project_id):
        if job.payload.get("scene_id") == scene_id and job.status in ("queued", "running"):
            return job
    return None


def render(ctx: AppContext, project_id: str, scene_id: str, *, reroll: bool = False) -> Job:
    story = require(ctx, project_id, scene_id)
    existing = _active_job(ctx, project_id, scene_id)
    if existing is not None:
        return existing
    f = shot_facts(ctx, project_id, story)[scene_id]
    if reroll and not shot_takes(ctx, project_id).get(scene_id):
        raise ShotError(409, "This scene has no shot yet.")
    _check_engine(ctx)
    if f.blockers:
        raise ShotError(409, BLOCKER_TEXT[f.blockers[0]])
    job = _enqueue(ctx, project_id, f, new_id(), 1, 1)
    frames_service.recompute_stage(ctx, project_id)
    return job


def render_all(
    ctx: AppContext, project_id: str, mode: str
) -> tuple[list[Job], list[dict[str, str]]]:
    story = require(ctx, project_id)
    _check_engine(ctx)
    cards = {s["scene_id"]: s for s in build_shots(ctx, project_id)}
    facts = shot_facts(ctx, project_id, story)
    busy = {
        str(j.payload.get("scene_id"))
        for j in shot_jobs(ctx, project_id)
        if j.status in ("queued", "running")
    }
    chosen: list[SceneShot] = []
    skipped: list[dict[str, str]] = []
    for sid, card in cards.items():
        wanted = (
            card["state"] == "stale"
            if mode == "stale"
            else not any(t["active"] for t in card["takes"])
        )
        if not wanted or sid in busy:
            continue
        f = facts[sid]
        if f.blockers:
            skipped.append({"scene_id": sid, "reason": f.blockers[0]})
        else:
            chosen.append(f)
    if not chosen:
        raise ShotError(409, "Nothing to generate.")
    batch = new_id()
    jobs = [_enqueue(ctx, project_id, f, batch, i, len(chosen)) for i, f in enumerate(chosen, 1)]
    frames_service.recompute_stage(ctx, project_id)
    return jobs, skipped


def retry_draft(ctx: AppContext, project_id: str, scene_id: str) -> Job:
    require(ctx, project_id, scene_id)
    update_slot(ctx, project_id, scene_id, quality="draft")
    return render(ctx, project_id, scene_id)


# ---- actions -------------------------------------------------------------------------------


def clear_approval(ctx: AppContext, project_id: str, scene_id: str) -> None:
    slot = get_slot(ctx, project_id, scene_id)
    if slot is not None and slot.approved_artifact_id is not None:
        update_slot(ctx, project_id, scene_id, approved_artifact_id=None)


def approve(ctx: AppContext, project_id: str, scene_id: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    card = next(s for s in build_shots(ctx, project_id) if s["scene_id"] == scene_id)
    active = next((t for t in card["takes"] if t["active"]), None)
    if active is None:
        raise ShotError(409, "This scene has no shot yet.")
    if active["stale"]:
        raise ShotError(409, "This shot is out of date. Render it again first.")
    update_slot(ctx, project_id, scene_id, approved_artifact_id=active["id"])
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)


def select_take(ctx: AppContext, project_id: str, scene_id: str, take_id: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    takes = shot_takes(ctx, project_id).get(scene_id, [])
    if take_id not in {t.id for t in takes}:
        raise ShotError(404, "take not found")
    with ctx.session_factory.begin() as s:
        for t in takes:
            row = s.get(Artifact, t.id)
            if row is not None:
                row.is_active = t.id == take_id
    clear_approval(ctx, project_id, scene_id)
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)


def set_type(ctx: AppContext, project_id: str, scene_id: str, shot_type: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    if shot_type not in shot_state.SHOT_TYPES:
        raise ShotError(422, "shot_type must be talking, action or continue")
    update_slot(ctx, project_id, scene_id, shot_type=shot_type, prompt_basis="")
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)


def set_quality(ctx: AppContext, project_id: str, scene_id: str, quality: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    if quality not in shot_state.QUALITIES:
        raise ShotError(422, "quality must be draft or final")
    update_slot(ctx, project_id, scene_id, quality=quality)
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)


def save_prompt(
    ctx: AppContext, project_id: str, scene_id: str, prompt: str, rerender: bool
) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    text = prompt.strip()
    if not text:
        raise ShotError(422, "The prompt can't be empty.")
    update_slot(ctx, project_id, scene_id, motion_prompt=text, prompt_source="user")
    if rerender:
        from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

        job = render(ctx, project_id, scene_id)
        return shot_response(ctx, project_id, scene_id, job=job_body(job))
    return shot_response(ctx, project_id, scene_id)


async def upload_clip(
    ctx: AppContext, project_id: str, scene_id: str, data: bytes
) -> dict[str, Any]:
    story = require(ctx, project_id, scene_id)
    clip = await screen_clip(ctx, data)
    f = shot_facts(ctx, project_id, story)[scene_id]
    last_png = ctx.settings.cache_tmp / f"{new_id()}.png"
    try:
        try:
            await extract_last_frame(clip.path, last_png)
        except NotAVideo:
            raise ShotError(415, NOT_VIDEO) from None
        take = ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=kinds.OWNER_SCENE,
                owner_id=scene_id,
                kind=kinds.SHOT_KIND,
                subdir=f"shots/{scene_id}",
                prompt="uploaded clip",
                seed=0,
                model_key="upload",
                model_revision="",
                adapter="upload",
                version="upload-1",
                params={
                    "source": "upload",
                    "inputs": [],
                    "shot_type": f.shot_type,
                    "quality": f.quality,
                },
                width=clip.info.width,
                height=clip.info.height,
                duration_s=clip.info.duration_s,
            ),
            clip.path,
            ext=clip.ext,
        )
        ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=kinds.OWNER_SCENE,
                owner_id=scene_id,
                kind=kinds.LAST_FRAME_KIND,
                subdir=f"shots/{scene_id}/last",
                prompt="last frame of the uploaded clip",
                seed=0,
                model_key="upload",
                model_revision="",
                adapter="ffmpeg",
                version="ffmpeg-1",
                params={"source": "ffmpeg", "inputs": [take.id]},
                input_artifact_ids=[take.id],
            ),
            last_png,
            ext="png",
        )
    finally:
        clip.path.unlink(missing_ok=True)
        last_png.unlink(missing_ok=True)
    clear_approval(ctx, project_id, scene_id)
    frames_service.recompute_stage(ctx, project_id)
    return shot_response(ctx, project_id, scene_id)
