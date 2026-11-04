"""Shot slots: per scene type and quality overrides, motion prompt and approval."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.config import Settings
from reelforge.db.models import ShotSlot, utcnow

if TYPE_CHECKING:
    from reelforge.context import AppContext

SHOT_JOB = "gen_shot"
SHOT_OOM_MESSAGE = "Killed, likely out of memory."
OOM_MARKER = "killed, likely out of memory"
SHOT_TYPES = ("talking", "action", "continue")
QUALITIES = ("draft", "final")
FPS = 24

# Seconds a shot takes on the reference Mac until real render times are recorded.
DEFAULT_ESTIMATE_S: dict[tuple[str, str], int] = {
    ("talking", "draft"): 180,
    ("action", "draft"): 150,
    ("continue", "draft"): 150,
    ("talking", "final"): 420,
    ("action", "final"): 360,
    ("continue", "final"): 360,
}


class ShotError(Exception):
    """A request problem; `status` and `message` become the HTTP response."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def get_slot(ctx: AppContext, project_id: str, key: str) -> ShotSlot | None:
    with ctx.session_factory() as s:
        return s.get(ShotSlot, (project_id, key))


def list_slots(ctx: AppContext, project_id: str) -> dict[str, ShotSlot]:
    with ctx.session_factory() as s:
        rows = s.scalars(select(ShotSlot).where(ShotSlot.project_id == project_id))
        return {r.story_key: r for r in rows}


def update_slot(ctx: AppContext, project_id: str, key: str, **values: Any) -> ShotSlot:
    """Create the slot when missing, then apply `values`."""
    with ctx.session_factory.begin() as s:
        slot = s.get(ShotSlot, (project_id, key))
        if slot is None:
            slot = ShotSlot(
                project_id=project_id,
                story_key=key,
                motion_prompt="",
                prompt_source="",
                prompt_basis="",
            )
            s.add(slot)
        for name, value in values.items():
            setattr(slot, name, value)
        slot.updated_at = utcnow()
        s.flush()
        s.expunge(slot)
    return slot


def size_for(settings: Settings, quality: str) -> tuple[int, int]:
    text = settings.shot_final_size if quality == "final" else settings.shot_draft_size
    width, _, height = text.partition("x")
    return int(width), int(height)


def effective_quality(settings: Settings, slot: ShotSlot | None) -> str:
    if slot is not None and slot.quality in QUALITIES:
        return slot.quality
    return settings.shot_quality


def is_oom(message: str) -> bool:
    return OOM_MARKER in message.lower()
