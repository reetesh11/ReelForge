"""Voice slots: the voice chosen for each story character, and the voice-model setting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from reelforge.adapters.mlx_audio import PRESETS, VOICE_MODELS
from reelforge.db.models import Setting, VoiceSlot, utcnow

if TYPE_CHECKING:
    from reelforge.context import AppContext

SETTING_KEY = "voice_model"
MODEL_LABELS = {"omnivoice": "OmniVoice", "kokoro": "Kokoro (fallback)"}
MODES = ("preset", "cloned", "recorded")


def current_voice_model(ctx: AppContext) -> str:
    """The runtime choice (settings table) when set, else `Settings.voice_model`."""
    with ctx.session_factory() as s:
        row = s.get(Setting, SETTING_KEY)
    if row is not None and isinstance(row.value, str) and row.value in VOICE_MODELS:
        return row.value
    return ctx.settings.voice_model


def set_voice_model(ctx: AppContext, key: str) -> None:
    with ctx.session_factory.begin() as s:
        row = s.get(Setting, SETTING_KEY)
        if row is None:
            s.add(Setting(key=SETTING_KEY, value=key))
        else:
            row.value = key


def model_id_of(ctx: AppContext, voice_model: str) -> str:
    key = VOICE_MODELS[voice_model]
    return ctx.registry.get(key).id if key in ctx.registry.keys() else ""


def voice_model_body(ctx: AppContext) -> dict[str, Any]:
    current = current_voice_model(ctx)
    return {
        "voice_model": current,
        "label": MODEL_LABELS[current],
        "model_id": model_id_of(ctx, current),
        "choices": [{"key": k, "label": MODEL_LABELS[k]} for k in VOICE_MODELS],
    }


def preset_ids(voice_model: str) -> list[str]:
    return [p.id for p in PRESETS[voice_model]]


def get_slot(ctx: AppContext, project_id: str, key: str) -> VoiceSlot | None:
    with ctx.session_factory() as s:
        return s.get(VoiceSlot, (project_id, key))


def list_slots(ctx: AppContext, project_id: str) -> dict[str, VoiceSlot]:
    with ctx.session_factory() as s:
        rows = s.scalars(select(VoiceSlot).where(VoiceSlot.project_id == project_id))
        return {r.story_key: r for r in rows}


def update_slot(ctx: AppContext, project_id: str, key: str, **values: Any) -> VoiceSlot:
    """Create the slot when missing, then apply `values`."""
    with ctx.session_factory.begin() as s:
        slot = s.get(VoiceSlot, (project_id, key))
        if slot is None:
            slot = VoiceSlot(
                project_id=project_id,
                story_key=key,
                mode="preset",
                reference_text="",
                speed=1.0,
                language="hi",
            )
            s.add(slot)
        for name, value in values.items():
            setattr(slot, name, value)
        slot.updated_at = utcnow()
        s.flush()
        s.expunge(slot)
    return slot


def delete_slot(ctx: AppContext, project_id: str, key: str) -> None:
    with ctx.session_factory.begin() as s:
        s.execute(
            delete(VoiceSlot).where(VoiceSlot.project_id == project_id, VoiceSlot.story_key == key)
        )


def voice_usable(slot: VoiceSlot | None) -> bool:
    """A voice that is complete enough to speak lines (recorded counts: lines are uploaded)."""
    if slot is None:
        return False
    if slot.mode == "preset":
        return bool(slot.voice_id)
    if slot.mode == "cloned":
        return bool(slot.reference_artifact_id) and bool(slot.reference_text.strip())
    return slot.mode == "recorded"


def voice_out(ctx: AppContext, slot: VoiceSlot) -> dict[str, Any]:
    mismatch = slot.model is not None and slot.model != current_voice_model(ctx)
    out: dict[str, Any] = {
        "mode": slot.mode,
        "model": slot.model,
        "voice_id": slot.voice_id,
        "reference_text": slot.reference_text,
        "speed": slot.speed,
        "language": slot.language,
        "model_mismatch": mismatch,
    }
    if slot.mode == "cloned" and slot.reference_artifact_id:
        out["reference_url"] = f"/media/{slot.reference_artifact_id}"
    if slot.clip_seconds is not None and slot.mode == "cloned":
        out["clip_seconds"] = slot.clip_seconds
    return out
