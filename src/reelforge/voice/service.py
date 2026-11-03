"""Voice stage operations: character voices, clip uploads and the voice board body."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reelforge.adapters.mlx_audio import PRESETS, check_speed
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state as cast_state
from reelforge.db.models import Project
from reelforge.ids import new_id
from reelforge.voice import slots
from reelforge.voice.slots import current_voice_model
from reelforge.voice.uploads import NotAnAudioClip, probe_seconds, sniff_audio

if TYPE_CHECKING:
    from reelforge.context import AppContext

VOICE_JOB = "gen_voice_take"
TAKE_KIND = "voice_take"
REF_KIND = "voice_reference"
OWNER_SCENE = "scene"
OWNER_CHARACTER = "character"
UNLOCKED_STAGES = (
    "CAST_APPROVED",
    "VOICES_APPROVED",
    "FRAMES_APPROVED",
    "SHOTS_APPROVED",
    "ASSEMBLED",
    "EXPORTED",
)
NOT_AUDIO = "That file isn't an audio clip."
CLONE_NEEDS = "Cloned voices need a clip and a transcript."
CLIP_RANGE_S = (5.0, 10.0)

__all__ = ["VOICE_JOB", "current_voice_model"]


class VoiceError(Exception):
    """A request problem; `status` and `message` become the HTTP response."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


class ProjectMissing(VoiceError):
    def __init__(self) -> None:
        super().__init__(404, "project not found")


class StageLocked(VoiceError):
    def __init__(self) -> None:
        super().__init__(409, "Approve the cast first.")


class UnknownCharacter(VoiceError):
    def __init__(self) -> None:
        super().__init__(404, "character not found")


def require(ctx: AppContext, project_id: str, key: str | None = None) -> cast_state.StoryCast:
    """Project exists, cast approved, and `key` (when given) is a story character."""
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None:
        raise ProjectMissing
    if project.stage not in UNLOCKED_STAGES:
        raise StageLocked
    story = cast_state.load_story_cast(ctx, project_id)
    if key is not None and key not in story.characters:
        raise UnknownCharacter
    return story


def project_stage(ctx: AppContext, project_id: str) -> str:
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
        return project.stage if project is not None else "DRAFT"


# ---- clip uploads --------------------------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    path: Path
    ext: str
    seconds: float


async def screen_clip(ctx: AppContext, data: bytes) -> Clip:
    """Check an uploaded clip by content; the file is left in `cache/tmp` for the store."""
    limit_mb = ctx.settings.max_upload_mb
    if len(data) > limit_mb * 1024 * 1024:
        raise VoiceError(413, f"That clip is larger than {limit_mb} MB.")
    try:
        ext = sniff_audio(data)
    except NotAnAudioClip:
        raise VoiceError(415, NOT_AUDIO) from None
    tmp_root = ctx.settings.cache_tmp
    tmp_root.mkdir(parents=True, exist_ok=True)
    path = tmp_root / f"{new_id()}.{ext}"
    path.write_bytes(data)
    try:
        seconds = await probe_seconds(path)
    except NotAnAudioClip:
        path.unlink(missing_ok=True)
        raise VoiceError(415, NOT_AUDIO) from None
    return Clip(path, ext, seconds)


# ---- character voices ----------------------------------------------------------------------


def _voice_key(slot: Any) -> tuple[Any, ...]:
    if slot is None:
        return ()
    return (
        slot.mode,
        slot.model,
        slot.voice_id,
        slot.reference_artifact_id,
        slot.reference_text,
        slot.speed,
    )


def set_character_voice(
    ctx: AppContext,
    project_id: str,
    key: str,
    *,
    mode: str,
    voice_id: str | None,
    reference_text: str | None,
    speed: float | None,
) -> dict[str, Any]:
    require(ctx, project_id, key)
    model = current_voice_model(ctx)
    before = slots.get_slot(ctx, project_id, key)
    if speed is not None:
        try:
            check_speed(speed)
        except ValueError as exc:
            raise VoiceError(422, str(exc)) from None
    new_speed = speed if speed is not None else (before.speed if before is not None else 1.0)
    values: dict[str, Any] = {"mode": mode, "speed": new_speed, "language": "hi"}
    if mode == "preset":
        if voice_id not in slots.preset_ids(model):
            label = slots.MODEL_LABELS[model]
            raise VoiceError(422, f"Pick one of the {label} preset voices.")
        values.update(model=model, voice_id=voice_id)
    elif mode == "cloned":
        text = (
            reference_text
            if reference_text is not None
            else (before.reference_text if before else "")
        )
        has_clip = before is not None and before.reference_artifact_id is not None
        if not has_clip or not text.strip():
            raise VoiceError(422, CLONE_NEEDS)
        values.update(model=model, voice_id=None, reference_text=text.strip())
    elif mode == "recorded":
        values.update(model=None, voice_id=None)
    else:
        raise VoiceError(422, "mode must be preset, cloned or recorded")
    after = slots.update_slot(ctx, project_id, key, **values)
    if _voice_key(before) != _voice_key(after):
        voice_changed(ctx, project_id, key)
    return slots.voice_out(ctx, after)


def clear_character_voice(ctx: AppContext, project_id: str, key: str) -> None:
    require(ctx, project_id, key)
    if slots.get_slot(ctx, project_id, key) is not None:
        slots.delete_slot(ctx, project_id, key)
        voice_changed(ctx, project_id, key)


def store_reference(
    ctx: AppContext, project_id: str, key: str, clip: Clip, reference_text: str | None
) -> dict[str, Any]:
    """Keep an accepted clip as the character's reference and switch them to a cloned voice."""
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
        adapter="upload",
        version="upload-1",
        duration_s=clip.seconds,
    )
    before = slots.get_slot(ctx, project_id, key)
    artifact = ctx.store.write(spec, clip.path, ext=clip.ext)
    text = reference_text.strip() if reference_text is not None else None
    values: dict[str, Any] = {
        "mode": "cloned",
        "model": current_voice_model(ctx),
        "voice_id": None,
        "reference_artifact_id": artifact.id,
        "clip_seconds": clip.seconds,
        "language": "hi",
    }
    if text is not None:
        values["reference_text"] = text
    after = slots.update_slot(ctx, project_id, key, **values)
    if _voice_key(before) != _voice_key(after):
        voice_changed(ctx, project_id, key)
    return slots.voice_out(ctx, after)


def voice_changed(ctx: AppContext, project_id: str, key: str) -> None:
    """A character's voice changed: hook for staling their lines and the library copy."""


# ---- the board body ------------------------------------------------------------------------


def characters_body(ctx: AppContext, project_id: str, story: cast_state.StoryCast) -> list[Any]:
    voices = slots.list_slots(ctx, project_id)
    cast_slots = cast_state.list_slots(ctx, project_id)
    out: list[dict[str, Any]] = []
    for key, char in story.characters.items():
        item: dict[str, Any] = {"key": key, "name": char.name}
        cast_slot = cast_slots.get(key)
        if cast_slot is not None and cast_slot.approved_artifact_id:
            item["avatar_url"] = f"/media/{cast_slot.approved_artifact_id}"
        slot = voices.get(key)
        item["voice"] = slots.voice_out(ctx, slot) if slot is not None else None
        out.append(item)
    return out


def voices_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    model = current_voice_model(ctx)
    return {
        "stage": project_stage(ctx, project_id),
        "voice_model": {
            "key": model,
            "label": slots.MODEL_LABELS[model],
            "model_id": slots.model_id_of(ctx, model),
        },
        "presets": [{"id": p.id, "label": p.label} for p in PRESETS[model]],
        "approved_count": 0,
        "total": 0,
        "stale_count": 0,
        "characters": characters_body(ctx, project_id, story),
        "lines": [],
        "job": None,
    }
