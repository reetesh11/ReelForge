"""Sound cue state: constants, errors, the picked take of each cue and the mix settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from reelforge.db.models import AudioSlot, Setting, utcnow

if TYPE_CHECKING:
    from reelforge.context import AppContext

AUDIO_JOB = "gen_audio_cue"
OWNER_CUE = "audio_cue"
TAKE_KIND = "audio_take"
NEEDS_APPROVAL = "Approve this cue before generating it."
NOT_AUDIO = "That file is not an audio clip."
DEFAULT_MIX: dict[str, float] = {
    "duck_db": 9.0,
    "attack_s": 0.15,
    "release_s": 0.4,
    "silence_fade_s": 0.08,
}
MAX_DUCK_DB = 40.0


class AudioError(Exception):
    """A request problem; `status` and `message` become the HTTP response."""

    def __init__(
        self, status: int, message: str, errors: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors


# ---- picked take ---------------------------------------------------------------------------


def get_slot(ctx: AppContext, project_id: str, cue_id: str) -> AudioSlot | None:
    with ctx.session_factory() as s:
        return s.get(AudioSlot, (project_id, cue_id))


def list_slots(ctx: AppContext, project_id: str) -> dict[str, AudioSlot]:
    with ctx.session_factory() as s:
        rows = s.scalars(select(AudioSlot).where(AudioSlot.project_id == project_id))
        return {r.cue_id: r for r in rows}


def set_picked(ctx: AppContext, project_id: str, cue_id: str, artifact_id: str | None) -> None:
    with ctx.session_factory.begin() as s:
        slot = s.get(AudioSlot, (project_id, cue_id))
        if slot is None:
            slot = AudioSlot(project_id=project_id, cue_id=cue_id)
            s.add(slot)
        slot.picked_artifact_id = artifact_id
        slot.updated_at = utcnow()


def drop_slot(ctx: AppContext, project_id: str, cue_id: str) -> None:
    with ctx.session_factory.begin() as s:
        slot = s.get(AudioSlot, (project_id, cue_id))
        if slot is not None:
            s.delete(slot)


# ---- mix settings --------------------------------------------------------------------------


def _mix_key(project_id: str) -> str:
    return f"audio_mix:{project_id}"


def get_mix_settings(ctx: AppContext, project_id: str) -> dict[str, float]:
    with ctx.session_factory() as s:
        row = s.get(Setting, _mix_key(project_id))
        raw: Any = row.value if row is not None else None
    stored: dict[str, Any] = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    out: dict[str, float] = {}
    for name, default in DEFAULT_MIX.items():
        value = stored.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool):
            out[name] = float(value)
        else:
            out[name] = default
    return out


def put_mix_settings(ctx: AppContext, project_id: str, **values: float) -> dict[str, float]:
    """Store the given settings (unknown names are refused) and return all four."""
    unknown = [k for k in values if k not in DEFAULT_MIX]
    if unknown:
        raise AudioError(422, f"unknown setting: {unknown[0]}")
    merged = {**get_mix_settings(ctx, project_id), **{k: float(v) for k, v in values.items()}}
    with ctx.session_factory.begin() as s:
        row = s.get(Setting, _mix_key(project_id))
        if row is None:
            s.add(Setting(key=_mix_key(project_id), value=merged))
        else:
            row.value = merged
    return merged
