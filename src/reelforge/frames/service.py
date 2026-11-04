"""Frames stage operations: the board body, staleness, generation requests and actions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.api.stages import STAGE_ORDER
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state as cast_state
from reelforge.cast.uploads import NotAnImage, TooLarge, sniff_image
from reelforge.db.models import Artifact, Job, Project, StoryChange, utcnow
from reelforge.frames import prompts
from reelforge.frames.product import locate_product
from reelforge.frames.state import (
    FRAME_JOB,
    FRAME_KIND,
    FRAMINGS,
    OWNER_SCENE,
    get_slot,
    list_slots,
    resolve_framing,
    update_slot,
)
from reelforge.ids import new_id
from reelforge.jobs.queue import JobStateError
from reelforge.shots import kinds as shot_kinds
from reelforge.story.markup import display_text
from reelforge.story.schema import Scene, Story
from reelforge.story.staleness import ChangeRow, is_stale
from reelforge.voice import service as voice_service

if TYPE_CHECKING:
    from reelforge.context import AppContext

NOT_IMAGE = "That file is not an image."
FRAMES_LOCKED = "Approve the voices first."
STALE_MESSAGE = "This frame is out of date. Make a new frame first."
NO_FRAME = "This scene has no frame yet."
APPROVED_STATES = ("approved", "continue_previous")


class FrameError(Exception):
    """A request problem; `status` and `message` become the HTTP response."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def stage_at_least(stage: str, wanted: str) -> bool:
    return STAGE_ORDER.index(stage) >= STAGE_ORDER.index(wanted)


def require(ctx: AppContext, project_id: str, scene_id: str | None = None) -> Story:
    """Project exists, voices approved, and `scene_id` (when given) is a scene of the story."""
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None:
        raise FrameError(404, "project not found")
    if not stage_at_least(project.stage, "VOICES_APPROVED"):
        raise FrameError(409, FRAMES_LOCKED)
    story = voice_service.load_story(ctx, project_id)
    if story is None:
        raise FrameError(409, FRAMES_LOCKED)
    if scene_id is not None and scene_id not in {s.id for s in story.scenes}:
        raise FrameError(404, "scene not found")
    return story


# ---- scene facts ---------------------------------------------------------------------------


def _mention_pos(text: str, words: list[str]) -> int | None:
    found: list[int] = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, flags=re.IGNORECASE)
        if match is not None:
            found.append(match.start())
    return min(found) if found else None


def characters_in_scene(story: Story, scene: Scene) -> list[str]:
    """Character keys in the scene: the speaker first, then others in order of first mention.
    A scene that names nobody falls back to the first character of the story."""
    keys: list[str] = []
    if scene.speaker and scene.speaker in story.characters:
        keys.append(scene.speaker)

    def mentioned_in(text: str) -> list[str]:
        found: list[tuple[int, str]] = []
        for key, char in story.characters.items():
            if key in keys:
                continue
            pos = _mention_pos(text, [char.name, key])
            if pos is not None:
                found.append((pos, key))
        return [key for _, key in sorted(found)]

    # Words in a spoken line only count when nobody is speaking: the speaker's line often
    # addresses someone who is not in the picture.
    keys += mentioned_in(" ".join(filter(None, [scene.action, scene.setting])))
    if not keys and scene.line:
        keys += mentioned_in(display_text(scene.line))
    if not keys and story.characters:
        keys.append(next(iter(story.characters)))
    return keys


def previous_scene_id(story: Story, scene_id: str) -> str | None:
    """The scene this one continues from: `continue_from`, else the scene before it."""
    ids = [s.id for s in story.scenes]
    scene = next(s for s in story.scenes if s.id == scene_id)
    if scene.continue_from in ids:
        return scene.continue_from
    index = ids.index(scene_id)
    return ids[index - 1] if index > 0 else None


@dataclass(frozen=True)
class Master:
    key: str
    name: str
    look: str
    artifact_id: str | None


@dataclass(frozen=True)
class SceneFacts:
    scene: Scene
    position: int
    framing: str
    master: Master | None
    others: list[tuple[str, str]]
    characters: list[Master]


def character_look(ctx: AppContext, project_id: str, story: Story, key: str) -> Master:
    char = story.characters[key]
    slot = cast_state.get_slot(ctx, project_id, key)
    look = (slot.bible_line if slot is not None and slot.bible_line.strip() else "") or char.look
    approved = slot.approved_artifact_id if slot is not None else None
    return Master(key, char.name, look, approved)


def scene_facts(ctx: AppContext, project_id: str, story: Story) -> dict[str, SceneFacts]:
    slots = list_slots(ctx, project_id)
    people = {k: character_look(ctx, project_id, story, k) for k in story.characters}
    out: dict[str, SceneFacts] = {}
    for position, scene in enumerate(story.scenes, start=1):
        keys = characters_in_scene(story, scene)
        chars = [people[k] for k in keys]
        master = chars[0] if chars else None
        out[scene.id] = SceneFacts(
            scene=scene,
            position=position,
            framing=resolve_framing(slots.get(scene.id), scene),
            master=master,
            others=[(c.name, c.look) for c in chars[1:]],
            characters=chars,
        )
    return out


def prompt_basis(story: Story, facts: SceneFacts, product: bool) -> str:
    master = facts.master
    parts = [
        facts.scene.action,
        facts.scene.setting or "",
        display_text(facts.scene.line or ""),
        facts.framing,
        story.style,
        master.look if master is not None else "",
        repr(facts.others),
        str(product),
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def default_prompt(story: Story, facts: SceneFacts, product: bool, sentence: str | None) -> str:
    master = facts.master
    return prompts.compose_frame_prompt(
        scene_sentence=sentence if sentence is not None else facts.scene.action,
        look=master.look if master is not None else "",
        framing=facts.framing,
        style=story.style,
        other_looks=facts.others,
        product=product,
    )


# ---- takes, jobs, changes ------------------------------------------------------------------


def frame_takes(ctx: AppContext, project_id: str) -> dict[str, list[Artifact]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_SCENE,
                Artifact.kind == FRAME_KIND,
            )
            .order_by(Artifact.take_no)
        )
        out: dict[str, list[Artifact]] = {}
        for r in rows:
            out.setdefault(r.owner_id, []).append(r)
    return out


def changes_by_scene(ctx: AppContext, project_id: str) -> dict[str, list[ChangeRow]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(StoryChange).where(
                StoryChange.project_id == project_id, StoryChange.owner_type == OWNER_SCENE
            )
        )
        out: dict[str, list[ChangeRow]] = {}
        for c in rows:
            out.setdefault(c.owner_id, []).append(
                ChangeRow(c.owner_type, c.owner_id, list(c.kinds), c.created_at)
            )
    return out


def jobs_of(ctx: AppContext, project_id: str, job_type: str) -> list[Job]:
    """Jobs of one type, newest first."""
    return [j for j in ctx.queue.list(project_id=project_id) if j.type == job_type]


def active_jobs(jobs: list[Job]) -> list[Job]:
    return [j for j in jobs if j.status in ("queued", "running")]


def job_state(
    jobs: list[Job], scene_id: str, active: Artifact | None
) -> tuple[str | None, str | None]:
    """(state, message) of the newest job for the scene when it is queued, running or failed."""
    for job in jobs:
        if job.payload.get("scene_id") != scene_id:
            continue
        if job.status == "queued":
            return "queued", None
        if job.status == "running":
            return "rendering", None
        if job.status == "failed":
            newer = active is not None and aware(active.created_at) > aware(job.created_at)
            if not newer:
                return "failed", job.error or "Couldn't generate."
        return None, None
    return None, None


# ---- the board -----------------------------------------------------------------------------


def take_stale(
    take: Artifact, changes: list[ChangeRow], framing: str, look: str, master_id: str | None
) -> bool:
    if is_stale(FRAME_KIND, aware(take.created_at), changes):
        return True
    params: dict[str, Any] = take.params or {}
    if params.get("source") == "upload":
        return False
    if params.get("framing") != framing:
        return True
    if master_id is not None and params.get("master_id") != master_id:
        return True
    return params.get("look") != look


def _take_out(t: Artifact, stale: bool, approved_id: str | None) -> dict[str, Any]:
    params: dict[str, Any] = t.params or {}
    return {
        "id": t.id,
        "take_no": t.take_no,
        "seed": t.seed,
        "active": t.is_active,
        "approved": t.id == approved_id,
        "stale": stale,
        "source": "upload" if params.get("source") == "upload" else "render",
        "image_url": f"/media/{t.id}",
        "inputs": list(params.get("inputs") or []),
    }


def previous_last_frame(
    ctx: AppContext, project_id: str, story: Story, scene_id: str
) -> Artifact | None:
    prev = previous_scene_id(story, scene_id)
    if prev is None:
        return None
    shot = shot_kinds.active_shot(ctx, project_id, prev)
    return shot_kinds.last_frame_for_take(ctx, shot.id) if shot is not None else None


def build_frames(ctx: AppContext, project_id: str) -> list[dict[str, Any]]:
    from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

    story = voice_service.load_story(ctx, project_id)
    if story is None:
        return []
    facts = scene_facts(ctx, project_id, story)
    slots = list_slots(ctx, project_id)
    takes = frame_takes(ctx, project_id)
    changes = changes_by_scene(ctx, project_id)
    jobs = jobs_of(ctx, project_id, FRAME_JOB)
    pack_ok = locate_product(ctx, story) is not None if story.product is not None else False
    out: list[dict[str, Any]] = []
    for sid, f in facts.items():
        slot = slots.get(sid)
        scene_takes = takes.get(sid, [])
        active = next((t for t in scene_takes if t.is_active), None)
        approved_id = slot.approved_artifact_id if slot is not None else None
        master = f.master
        master_id = master.artifact_id if master is not None else None
        look = master.look if master is not None else ""
        ch = changes.get(sid, [])
        stale_by_id = {t.id: take_stale(t, ch, f.framing, look, master_id) for t in scene_takes}
        continue_prev = bool(slot.continue_previous) if slot is not None else False
        has_product = bool(f.scene.product_in_shot)
        product = has_product and story.product is not None
        shown_prompt = ""
        source = slot.prompt_source if slot is not None else ""
        if slot is not None and slot.prompt.strip():
            shown_prompt = slot.prompt
        elif master is not None:
            shown_prompt = default_prompt(story, f, product and pack_ok, None)
        notes: dict[str, Any] = {}
        if master is not None and f.others:
            notes["second_character"] = {"master_name": master.name, "other_name": f.others[0][0]}
        if has_product:
            notes["product"] = "included" if (product and pack_ok) else "missing"
        if not f.characters:
            notes["no_character"] = True
        elif master is not None and master_id is None:
            notes["needs_master"] = master.name
        waiting = False
        if continue_prev:
            waiting = previous_last_frame(ctx, project_id, story, sid) is None
            if waiting:
                notes["waiting_for_previous_shot"] = True
        job_s, job_message = job_state(jobs, sid, active)
        message: str | None = None
        if continue_prev:
            state = "continue_previous"
        elif job_s in ("queued", "rendering"):
            state = job_s or "queued"
        elif job_s == "failed":
            state, message = "failed", job_message
        elif active is None:
            state = "no_frame"
        elif stale_by_id[active.id]:
            state = "stale"
        elif approved_id == active.id:
            state = "approved"
        else:
            state = "ready"
        active_jobs_here = [j for j in active_jobs(jobs) if j.payload.get("scene_id") == sid]
        card: dict[str, Any] = {
            "scene_id": sid,
            "position": f.position,
            "characters": [{"key": c.key, "name": c.name} for c in f.characters],
            "master": (
                {"key": master.key, "name": master.name, "artifact_id": master_id}
                if master is not None and master_id is not None
                else None
            ),
            "framing": f.framing,
            "state": state,
            "prompt": shown_prompt,
            "prompt_source": source if source in ("llm", "user") else "",
            "look_removed": bool(shown_prompt.strip() and look and look not in shown_prompt),
            "takes": [_take_out(t, stale_by_id[t.id], approved_id) for t in scene_takes],
            "notes": notes,
            "continue_previous": continue_prev,
            "job": job_body(active_jobs_here[0]) if active_jobs_here else None,
        }
        if message:
            card["message"] = message
        out.append(card)
    return out


def counts(frames: list[dict[str, Any]]) -> tuple[int, int, int]:
    return (
        sum(1 for f in frames if f["state"] in APPROVED_STATES),
        len(frames),
        sum(1 for f in frames if f["state"] == "stale"),
    )


def frames_complete(frames: list[dict[str, Any]]) -> bool:
    return bool(frames) and all(f["state"] in APPROVED_STATES for f in frames)


def recompute_stage(ctx: AppContext, project_id: str) -> str:
    """Move between VOICES_APPROVED, FRAMES_APPROVED and SHOTS_APPROVED to match the work;
    never touches earlier or later stages."""
    from reelforge.shots import service as shots_service  # noqa: PLC0415

    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None:
        raise FrameError(404, "project not found")
    managed = ("VOICES_APPROVED", "FRAMES_APPROVED", "SHOTS_APPROVED")
    if project.stage not in managed:
        return project.stage
    frames_ok = frames_complete(build_frames(ctx, project_id))
    shots_ok = frames_ok and shots_service.shots_complete(ctx, project_id)
    target = "VOICES_APPROVED"
    if frames_ok:
        target = "SHOTS_APPROVED" if shots_ok else "FRAMES_APPROVED"
    if target == project.stage:
        return target
    with ctx.session_factory.begin() as s:
        row = s.get(Project, project_id)
        if row is None:
            raise FrameError(404, "project not found")
        row.stage = target
        row.updated_at = utcnow()
    ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": target})
    return target


def frames_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

    require(ctx, project_id)
    frames = build_frames(ctx, project_id)
    approved, total, stale = counts(frames)
    order = {f["scene_id"]: f["position"] for f in frames}
    jobs = sorted(
        active_jobs(jobs_of(ctx, project_id, FRAME_JOB)),
        key=lambda j: order.get(str(j.payload.get("scene_id")), 0),
    )
    return {
        "stage": voice_service.project_stage(ctx, project_id),
        "approved_count": approved,
        "total": total,
        "stale_count": stale,
        "jobs": [job_body(j) for j in jobs],
        "frames": frames,
    }


# ---- generation requests -------------------------------------------------------------------


def _enqueue(
    ctx: AppContext, project_id: str, scene_id: str, batch_id: str, index: int, total: int
) -> Job:
    return ctx.queue.enqueue(
        type=FRAME_JOB,
        project_id=project_id,
        payload={
            "stage": "frames",
            "scene_id": scene_id,
            "batch_id": batch_id,
            "index": index,
            "total": total,
        },
        heavy=True,
        mem_need_gb=ctx.settings.image_mem_gb,
    )


def plan_generation(
    ctx: AppContext, project_id: str, mode: str, wanted: list[str] | None
) -> tuple[list[str], list[dict[str, str]]]:
    story = require(ctx, project_id)
    frames = {f["scene_id"]: f for f in build_frames(ctx, project_id)}
    busy = {
        str(j.payload.get("scene_id")) for j in active_jobs(jobs_of(ctx, project_id, FRAME_JOB))
    }
    if mode == "scenes":
        unknown = [w for w in (wanted or []) if w not in frames]
        if unknown:
            raise FrameError(404, "scene not found")
        candidates = [sid for sid in frames if sid in (wanted or [])]
    elif mode == "stale":
        candidates = [sid for sid, f in frames.items() if f["state"] == "stale"]
    else:
        candidates = [sid for sid, f in frames.items() if not any(t["active"] for t in f["takes"])]
    facts = scene_facts(ctx, project_id, story)
    ids: list[str] = []
    skipped: list[dict[str, str]] = []
    for sid in candidates:
        if sid in busy:
            continue
        master = facts[sid].master
        if frames[sid]["continue_previous"]:
            skipped.append({"scene_id": sid, "reason": "continue_previous"})
        elif master is None or master.artifact_id is None:
            skipped.append({"scene_id": sid, "reason": "needs_master"})
        else:
            ids.append(sid)
    return ids, skipped


def enqueue_generation(
    ctx: AppContext, project_id: str, mode: str, wanted: list[str] | None
) -> tuple[list[Job], list[dict[str, str]]]:
    ids, skipped = plan_generation(ctx, project_id, mode, wanted)
    if not ids:
        raise FrameError(409, "Nothing to generate.")
    batch = new_id()
    jobs = [_enqueue(ctx, project_id, sid, batch, i, len(ids)) for i, sid in enumerate(ids, 1)]
    recompute_stage(ctx, project_id)
    return jobs, skipped


def enqueue_scene(ctx: AppContext, project_id: str, scene_id: str) -> Job:
    story = require(ctx, project_id, scene_id)
    for job in active_jobs(jobs_of(ctx, project_id, FRAME_JOB)):
        if job.payload.get("scene_id") == scene_id:
            return job
    slot = get_slot(ctx, project_id, scene_id)
    if slot is not None and slot.continue_previous:
        raise FrameError(409, "This scene continues from the previous shot.")
    master = scene_facts(ctx, project_id, story)[scene_id].master
    if master is None:
        raise FrameError(409, "There is no character in this scene.")
    if master.artifact_id is None:
        raise FrameError(409, f"Approve a master for {master.name} in Cast first")
    job = _enqueue(ctx, project_id, scene_id, new_id(), 1, 1)
    recompute_stage(ctx, project_id)
    return job


def cancel_all(ctx: AppContext, project_id: str) -> int:
    require(ctx, project_id)
    jobs = active_jobs(jobs_of(ctx, project_id, FRAME_JOB))
    jobs.sort(key=lambda j: j.status != "queued")
    count = 0
    for job in jobs:
        try:
            ctx.queue.cancel(job.id)
            count += 1
        except JobStateError:  # finished in the meantime
            continue
    recompute_stage(ctx, project_id)
    return count


# ---- scene actions -------------------------------------------------------------------------


def frame_response(ctx: AppContext, project_id: str, scene_id: str, **extra: Any) -> dict[str, Any]:
    frames = build_frames(ctx, project_id)
    approved, total, _ = counts(frames)
    card = next(f for f in frames if f["scene_id"] == scene_id)
    return {
        "project_stage": voice_service.project_stage(ctx, project_id),
        "approved_count": approved,
        "total": total,
        "frame": card,
        **extra,
    }


def clear_approval(ctx: AppContext, project_id: str, scene_id: str) -> None:
    slot = get_slot(ctx, project_id, scene_id)
    if slot is not None and slot.approved_artifact_id is not None:
        update_slot(ctx, project_id, scene_id, approved_artifact_id=None)


def select_take(ctx: AppContext, project_id: str, scene_id: str, take_id: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    takes = frame_takes(ctx, project_id).get(scene_id, [])
    if take_id not in {t.id for t in takes}:
        raise FrameError(404, "take not found")
    with ctx.session_factory.begin() as s:
        for t in takes:
            row = s.get(Artifact, t.id)
            if row is not None:
                row.is_active = t.id == take_id
    clear_approval(ctx, project_id, scene_id)
    recompute_stage(ctx, project_id)
    return frame_response(ctx, project_id, scene_id)


def approve(ctx: AppContext, project_id: str, scene_id: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    card = next(f for f in build_frames(ctx, project_id) if f["scene_id"] == scene_id)
    active = next((t for t in card["takes"] if t["active"]), None)
    if active is None:
        raise FrameError(409, NO_FRAME)
    if active["stale"]:
        raise FrameError(409, STALE_MESSAGE)
    update_slot(ctx, project_id, scene_id, approved_artifact_id=active["id"])
    recompute_stage(ctx, project_id)
    return frame_response(ctx, project_id, scene_id)


def set_framing(ctx: AppContext, project_id: str, scene_id: str, framing: str) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    if framing not in FRAMINGS:
        raise FrameError(422, "framing must be wide, medium or closeup")
    update_slot(ctx, project_id, scene_id, framing=framing)
    recompute_stage(ctx, project_id)
    return frame_response(ctx, project_id, scene_id)


def save_prompt(
    ctx: AppContext, project_id: str, scene_id: str, prompt: str, regenerate: bool
) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    text = prompt.strip()
    if not text:
        raise FrameError(422, "The prompt can't be empty.")
    update_slot(ctx, project_id, scene_id, prompt=text, prompt_source="user", prompt_basis="")
    if regenerate:
        job = enqueue_scene(ctx, project_id, scene_id)
        from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

        return frame_response(ctx, project_id, scene_id, job=job_body(job))
    return frame_response(ctx, project_id, scene_id)


def set_continue_previous(
    ctx: AppContext, project_id: str, scene_id: str, enabled: bool
) -> dict[str, Any]:
    story = require(ctx, project_id, scene_id)
    if enabled and previous_scene_id(story, scene_id) is None:
        raise FrameError(409, "The first scene has no previous shot.")
    update_slot(ctx, project_id, scene_id, continue_previous=enabled)
    recompute_stage(ctx, project_id)
    return frame_response(ctx, project_id, scene_id)


# ---- uploads -------------------------------------------------------------------------------


def upload_frame(ctx: AppContext, project_id: str, scene_id: str, data: bytes) -> dict[str, Any]:
    require(ctx, project_id, scene_id)
    limit_mb = ctx.settings.max_upload_mb
    if len(data) > limit_mb * 1024 * 1024:
        raise FrameError(413, f"That image is larger than {limit_mb} MB.")
    try:
        ext, width, height = sniff_image(data)
    except NotAnImage:
        raise FrameError(415, NOT_IMAGE) from None
    except TooLarge:
        raise FrameError(413, "That image is too large in pixels.") from None
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=OWNER_SCENE,
        owner_id=scene_id,
        kind=FRAME_KIND,
        subdir=f"frames/{scene_id}",
        prompt="uploaded frame",
        seed=0,
        model_key="upload",
        model_revision="",
        adapter="upload",
        version="upload-1",
        params={"source": "upload", "inputs": []},
        width=width,
        height=height,
    )
    ctx.store.write(spec, data, ext=ext)
    clear_approval(ctx, project_id, scene_id)
    recompute_stage(ctx, project_id)
    return frame_response(ctx, project_id, scene_id)


# ---- key frame for the shots stage ---------------------------------------------------------


def key_frame(ctx: AppContext, project_id: str, story: Story, scene_id: str) -> Artifact | None:
    """The image a shot starts from: the previous shot's last frame for a continued scene,
    else the scene's active frame take."""
    slot = get_slot(ctx, project_id, scene_id)
    if slot is not None and slot.continue_previous:
        return previous_last_frame(ctx, project_id, story, scene_id)
    return next((t for t in frame_takes(ctx, project_id).get(scene_id, []) if t.is_active), None)
