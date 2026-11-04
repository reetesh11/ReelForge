"""Shots stage operations: scene facts, blockers and staleness, then the board and actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.db.models import Artifact, Project, ShotSlot
from reelforge.frames import service as frames_service
from reelforge.shots import kinds
from reelforge.shots import state as shot_state
from reelforge.shots.state import SHOT_JOB, effective_quality, list_slots, size_for
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


class ShotError(Exception):
    """A request problem; `status` and `message` become the HTTP response."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


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


def shots_complete(ctx: AppContext, project_id: str) -> bool:
    return False
