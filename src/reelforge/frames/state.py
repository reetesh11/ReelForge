"""Frame slots: per scene framing, prompt and approval, plus the job-type constant."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.db.models import FrameSlot, utcnow
from reelforge.story.schema import Scene

if TYPE_CHECKING:
    from reelforge.context import AppContext

FRAME_JOB = "gen_frame"
FRAME_KIND = "frame"
PACK_KIND = "product_pack"
OWNER_SCENE = "scene"
OWNER_PROJECT = "project"
PACK_OWNER_ID = "product"
FRAMINGS = ("wide", "medium", "closeup")
FRAME_STRENGTH = 0.6
FRAME_WIDTH = 576
FRAME_HEIGHT = 1024


def get_slot(ctx: AppContext, project_id: str, key: str) -> FrameSlot | None:
    with ctx.session_factory() as s:
        return s.get(FrameSlot, (project_id, key))


def list_slots(ctx: AppContext, project_id: str) -> dict[str, FrameSlot]:
    with ctx.session_factory() as s:
        rows = s.scalars(select(FrameSlot).where(FrameSlot.project_id == project_id))
        return {r.story_key: r for r in rows}


def update_slot(ctx: AppContext, project_id: str, key: str, **values: Any) -> FrameSlot:
    """Create the slot when missing, then apply `values`."""
    with ctx.session_factory.begin() as s:
        slot = s.get(FrameSlot, (project_id, key))
        if slot is None:
            slot = FrameSlot(
                project_id=project_id,
                story_key=key,
                prompt="",
                prompt_source="",
                prompt_basis="",
                continue_previous=False,
            )
            s.add(slot)
        for name, value in values.items():
            setattr(slot, name, value)
        slot.updated_at = utcnow()
        s.flush()
        s.expunge(slot)
    return slot


def resolve_framing(slot: FrameSlot | None, scene: Scene) -> str:
    """The user's choice, then the story's, then closeup for dialogue and medium otherwise."""
    if slot is not None and slot.framing in FRAMINGS:
        return slot.framing
    if scene.framing is not None:
        return scene.framing
    return "closeup" if (scene.line or "").strip() else "medium"
