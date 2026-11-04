"""Voice slots: the voice chosen for each story character, and the voice-model setting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from reelforge.adapters.mlx_audio import PRESETS, VOICE_MODELS
from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Artifact, Setting, VoiceSlot, utcnow
from reelforge.library import service as library

if TYPE_CHECKING:
    from reelforge.context import AppContext

SETTING_KEY = "voice_model"
MODEL_LABELS = {"omnivoice": "OmniVoice", "kokoro": "Kokoro (fallback)"}
MODES = ("preset", "cloned", "recorded")
REF_KIND = "voice_reference"
OWNER_CHARACTER = "character"


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


def sync_to_library(ctx: AppContext, project_id: str, key: str, character_id: str) -> None:
    """Copy the project voice (and its clip) onto the library character."""
    slot = get_slot(ctx, project_id, key)
    if slot is None:
        library.set_voice(ctx, character_id, None)
        return
    ref_path: str | None = None
    sha: str | None = None
    if slot.mode == "cloned" and slot.reference_artifact_id:
        with ctx.session_factory() as s:
            art = s.get(Artifact, slot.reference_artifact_id)
        if art is not None and ctx.store.absolute_path(art).is_file():
            ref_path, sha = library.store_voice_reference(
                ctx, character_id, ctx.store.absolute_path(art)
            )
    library.set_voice(
        ctx,
        character_id,
        {
            "mode": slot.mode,
            "model": slot.model,
            "voice_id": slot.voice_id,
            "reference_path": ref_path,
            "reference_sha256": sha,
            "reference_text": slot.reference_text,
            "speed": slot.speed,
            "language": slot.language,
        },
        clip_seconds=slot.clip_seconds,
    )


def adopt_from_library(ctx: AppContext, project_id: str, key: str, character_id: str) -> None:
    """Copy a library character's voice settings and clip into the project."""
    voice = library.get_voice(ctx, character_id)
    if voice is None:
        return
    artifact_id: str | None = None
    if voice["mode"] == "cloned" and voice["reference_path"]:
        src = ctx.settings.data_root / voice["reference_path"]
        if src.is_file():
            seconds = library.voice_clip_seconds(ctx, character_id)
            spec = ArtifactSpec(
                project_id=project_id,
                owner_type=OWNER_CHARACTER,
                owner_id=key,
                kind=REF_KIND,
                subdir=f"voices/{key}",
                prompt="voice reference clip",
                seed=0,
                model_key="upload",
                model_revision="",
                adapter="library",
                version="library-1",
                duration_s=seconds,
            )
            artifact_id = ctx.store.write(
                spec, src.read_bytes(), ext=src.suffix.lstrip(".") or "wav"
            ).id
    update_slot(
        ctx,
        project_id,
        key,
        mode=voice["mode"],
        model=voice["model"],
        voice_id=voice["voice_id"],
        reference_artifact_id=artifact_id,
        reference_text=voice["reference_text"],
        speed=voice["speed"],
        language=voice["language"],
        clip_seconds=library.voice_clip_seconds(ctx, character_id),
    )
