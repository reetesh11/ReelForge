"""Voice stage operations: character voices, clip uploads and the voice board body."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from reelforge.adapters.mlx_audio import PRESETS, check_speed
from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import service as cast_service
from reelforge.cast import state as cast_state
from reelforge.db.models import (
    Artifact,
    Job,
    Line,
    Project,
    Scene,
    StoryChange,
    VoiceSlot,
    utcnow,
)
from reelforge.ids import new_id
from reelforge.story import service as story_service
from reelforge.story.schema import Story
from reelforge.story.staleness import ChangeRow, is_stale
from reelforge.story.yamlio import parse_story
from reelforge.voice import slots
from reelforge.voice.slots import current_voice_model
from reelforge.voice.uploads import NotAnAudioClip, probe_seconds, sniff_audio

if TYPE_CHECKING:
    from reelforge.context import AppContext

VOICE_JOB = "gen_voice_take"
TAKE_KIND = "voice_take"
REF_KIND = slots.REF_KIND
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


def sync_library(ctx: AppContext, project_id: str, key: str) -> None:
    """Keep the linked library character's voice equal to the project voice."""
    if cast_state.get_slot(ctx, project_id, key) is None:
        return
    cast_service.ensure_own_character(ctx, project_id, key)
    linked = cast_service.linked_character(ctx, project_id, key)
    if linked is not None:
        slots.sync_to_library(ctx, project_id, key, linked.id)


def voice_changed(ctx: AppContext, project_id: str, key: str) -> None:
    """A character's voice changed: stale and reopen their lines, then update the library."""
    story = load_story(ctx, project_id)
    if story is not None:
        ensure_rows(ctx, project_id)
        takes = takes_by_scene(ctx, project_id)
        now = utcnow()
        version = story_service.current_version(ctx, project_id)
        with ctx.session_factory.begin() as s:
            for scene in story.scenes:
                if scene.speaker != key:
                    continue
                sc = s.scalars(
                    select(Scene).where(Scene.project_id == project_id, Scene.story_key == scene.id)
                ).one()
                line = s.scalars(select(Line).where(Line.scene_id == sc.id)).one()
                line.approved_artifact_id = None
                if version is not None and (takes.get(scene.id) or sc.shot_length_at is not None):
                    s.add(
                        StoryChange(
                            project_id=project_id,
                            story_version_id=version.id,
                            owner_type=OWNER_SCENE,
                            owner_id=scene.id,
                            kinds=["voice_take", "shot"],
                            created_at=now,
                        )
                    )
        recompute_stage(ctx, project_id)
    sync_library(ctx, project_id, key)


# ---- story, rows and takes -----------------------------------------------------------------


def load_story(ctx: AppContext, project_id: str) -> Story | None:
    current = story_service.current_version(ctx, project_id)
    if current is None:
        return None
    try:
        return parse_story(current.yaml_text)
    except Exception:  # noqa: BLE001 - an unreadable story shows an empty board
        return None


def ensure_rows(ctx: AppContext, project_id: str) -> None:
    """Create the `scenes` and `lines` rows for every scene of the current story."""
    story = load_story(ctx, project_id)
    if story is None:
        return
    with ctx.session_factory.begin() as s:
        scenes = {
            r.story_key: r for r in s.scalars(select(Scene).where(Scene.project_id == project_id))
        }
        for position, scene in enumerate(story.scenes, start=1):
            row = scenes.get(scene.id)
            if row is None:
                row = Scene(
                    id=new_id(), project_id=project_id, story_key=scene.id, position=position
                )
                s.add(row)
                s.flush()
                s.add(Line(scene_id=row.id, text=scene.line or "", language="hi"))
                continue
            row.position = position
            line = s.scalars(select(Line).where(Line.scene_id == row.id)).first()
            if line is None:
                s.add(Line(scene_id=row.id, text=scene.line or "", language="hi"))
            elif line.text != (scene.line or ""):
                line.text = scene.line or ""


def takes_by_scene(ctx: AppContext, project_id: str) -> dict[str, list[Artifact]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_SCENE,
                Artifact.kind == TAKE_KIND,
            )
            .order_by(Artifact.take_no)
        )
        out: dict[str, list[Artifact]] = {}
        for r in rows:
            out.setdefault(r.owner_id, []).append(r)
    return out


def _changes_by_scene(ctx: AppContext, project_id: str) -> dict[str, list[ChangeRow]]:
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


def voice_jobs(ctx: AppContext, project_id: str) -> list[Job]:
    """Generation jobs (not preset previews), newest first."""
    return [
        j
        for j in ctx.queue.list(project_id=project_id)
        if j.type == VOICE_JOB and not j.payload.get("preview")
    ]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass
class LineInput:
    scene_id: str
    text: str
    speaker: str | None
    speaker_name: str | None
    slot: VoiceSlot | None
    speed: float
    pause_before: float
    pause_after: float
    budget_s: float | None
    approved_artifact_id: str | None
    scene_frames: int | None
    scene_shot_at: datetime | None
    position: int


def line_inputs(ctx: AppContext, project_id: str) -> dict[str, LineInput]:
    story = load_story(ctx, project_id)
    if story is None:
        return {}
    ensure_rows(ctx, project_id)
    voices = slots.list_slots(ctx, project_id)
    out: dict[str, LineInput] = {}
    with ctx.session_factory() as s:
        scenes = {
            r.story_key: r for r in s.scalars(select(Scene).where(Scene.project_id == project_id))
        }
        lines = {
            ln.scene_id: ln
            for ln in s.scalars(
                select(Line).where(Line.scene_id.in_([sc.id for sc in scenes.values()]))
            )
        }
    for position, scene in enumerate(story.scenes, start=1):
        row = scenes[scene.id]
        line = lines[row.id]
        speaker = scene.speaker
        char = story.characters.get(speaker) if speaker else None
        out[scene.id] = LineInput(
            scene_id=scene.id,
            text=(scene.line or "").strip(),
            speaker=speaker,
            speaker_name=char.name if char is not None else None,
            slot=voices.get(speaker) if speaker else None,
            speed=line.speed,
            pause_before=line.pause_before,
            pause_after=line.pause_after,
            budget_s=scene.duration,
            approved_artifact_id=line.approved_artifact_id,
            scene_frames=row.frames,
            scene_shot_at=row.shot_length_at,
            position=position,
        )
    return out


def next_take_no(ctx: AppContext, project_id: str, scene_id: str) -> int:
    with ctx.session_factory() as s:
        top = s.scalar(
            select(func.max(Artifact.take_no)).where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_SCENE,
                Artifact.owner_id == scene_id,
                Artifact.kind == TAKE_KIND,
            )
        )
    return (top or 0) + 1


def write_take(
    ctx: AppContext,
    project_id: str,
    scene_id: str,
    path: Path,
    *,
    duration_s: float,
    text: str,
    speed: float,
    voice: dict[str, Any],
    source: str,
    model_key: str,
    model_id: str,
    revision: str,
    adapter: str,
    version: str,
    inputs: list[str],
    job_id: str | None,
) -> Artifact:
    """Store a processed WAV as the line's new active take and reopen the line."""
    take_no = next_take_no(ctx, project_id, scene_id)
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=OWNER_SCENE,
        owner_id=scene_id,
        kind=TAKE_KIND,
        subdir=f"voices/lines/{scene_id}",
        prompt=text,
        seed=cast_state.derive_seed(project_id, f"{scene_id}:{take_no}"),
        model_key=model_key,
        model_id=model_id,
        model_revision=revision,
        adapter=adapter,
        version=version,
        params={"text": text, "speed": speed, "voice": voice, "source": source},
        input_artifact_ids=inputs,
        job_id=job_id,
        duration_s=duration_s,
    )
    artifact = ctx.store.write(spec, path, ext="wav")
    clear_approval(ctx, project_id, scene_id)
    recompute_stage(ctx, project_id)
    return artifact


def clear_approval(ctx: AppContext, project_id: str, scene_id: str) -> None:
    with ctx.session_factory.begin() as s:
        row = s.scalars(
            select(Scene).where(Scene.project_id == project_id, Scene.story_key == scene_id)
        ).first()
        if row is None:
            return
        line = s.scalars(select(Line).where(Line.scene_id == row.id)).first()
        if line is not None:
            line.approved_artifact_id = None


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


# ---- line board ----------------------------------------------------------------------------


def _take_out(
    t: Artifact, text: str, changes: list[ChangeRow], approved_id: str | None
) -> dict[str, Any]:
    stale = (
        is_stale(TAKE_KIND, _aware(t.created_at), changes) or (t.params or {}).get("text") != text
    )
    return {
        "id": t.id,
        "take_no": t.take_no,
        "seed": t.seed,
        "duration_s": t.duration_s,
        "active": t.is_active,
        "approved": t.id == approved_id,
        "stale": bool(stale),
        "audio_url": f"/media/{t.id}",
    }


def _line_job_state(
    jobs: list[Job], scene_id: str, active: Artifact | None
) -> tuple[str | None, str | None]:
    """(state, message) when the newest job covering this line is running or failed it."""
    for job in jobs:
        if scene_id not in (job.payload.get("scene_ids") or []):
            continue
        result: dict[str, Any] = job.result or {}
        done_lines: dict[str, Any] = result.get("lines") or {}
        done: dict[str, Any] | None = done_lines.get(scene_id)
        if job.status == "queued":
            return "queued", None
        if job.status == "running":
            return ("rendering", None) if done is None else (None, None)
        if done is not None and done.get("status") == "failed":
            newer = active is not None and _aware(active.created_at) > _aware(job.created_at)
            if not newer:
                return "failed", str(done.get("error") or "Couldn't generate this line.")
        elif job.status == "failed" and done is None:
            newer = active is not None and _aware(active.created_at) > _aware(job.created_at)
            if not newer:
                return "failed", job.error or "Couldn't generate this line."
        return None, None
    return None, None


def build_lines(ctx: AppContext, project_id: str) -> list[dict[str, Any]]:
    from reelforge.voice.frames import shot_length_s  # noqa: PLC0415

    inputs = line_inputs(ctx, project_id)
    takes = takes_by_scene(ctx, project_id)
    changes = _changes_by_scene(ctx, project_id)
    jobs = voice_jobs(ctx, project_id)
    out: list[dict[str, Any]] = []
    for sid, li in inputs.items():
        scene_takes = takes.get(sid, [])
        active = next((t for t in scene_takes if t.is_active), None)
        ch = changes.get(sid, [])
        take_items = [_take_out(t, li.text, ch, li.approved_artifact_id) for t in scene_takes]
        active_item = next((t for t in take_items if t["active"]), None)
        line: dict[str, Any] = {
            "scene_id": sid,
            "position": li.position,
            "speaker": li.speaker,
            "text": li.text,
            "language": "hi",
            "speed": li.speed,
            "pause_before": li.pause_before,
            "pause_after": li.pause_after,
            "takes": take_items,
            "shot_length_stale": False,
        }
        if li.speaker_name:
            line["speaker_name"] = li.speaker_name
        total_s: float | None = None
        if active is not None and active.duration_s is not None:
            total_s = active.duration_s + li.pause_before + li.pause_after
            line["duration_s"] = total_s
        if li.scene_frames is not None and li.scene_shot_at is not None:
            line["frames"] = li.scene_frames
            line["shot_length_s"] = shot_length_s(li.scene_frames)
            shot_changes = [c for c in ch if "*" in c.kinds or "shot" in c.kinds]
            latest = max((c.created_at for c in shot_changes), default=None)
            if latest is not None and _aware(latest) > _aware(li.scene_shot_at):
                newer_take = active is not None and _aware(active.created_at) > _aware(latest)
                line["shot_length_stale"] = not newer_take
        if total_s is not None and li.budget_s is not None and total_s > li.budget_s + 1e-6:
            line["over_budget"] = {"line_s": total_s, "budget_s": li.budget_s}
        state, message = _resolve_state(li, active, active_item, jobs)
        line["state"] = state
        if message:
            line["message"] = message
        out.append(line)
    return out


def _resolve_state(
    li: LineInput, active: Artifact | None, active_item: dict[str, Any] | None, jobs: list[Job]
) -> tuple[str, str | None]:
    if not li.text:
        return "no_dialogue", None
    if not slots.voice_usable(li.slot):
        who = li.speaker_name or "this line"
        return "no_voice", f"Pick a voice for {who}"
    job_state, job_message = _line_job_state(jobs, li.scene_id, active)
    if job_state in ("queued", "rendering"):
        return job_state, None
    if job_state == "failed":
        return "failed", job_message
    if active_item is None:
        return "no_take", None
    if active_item["stale"]:
        return "stale", None
    if active is not None and li.approved_artifact_id == active.id:
        return "approved", None
    return "ready", None


def recompute_stage(ctx: AppContext, project_id: str) -> str:
    """VOICES_APPROVED iff every line with text is approved; never touches other stages."""
    lines = build_lines(ctx, project_id)
    texted = [ln for ln in lines if ln["state"] != "no_dialogue"]
    complete = bool(texted) and all(ln["state"] == "approved" for ln in texted)
    new_stage: str | None = None
    with ctx.session_factory.begin() as s:
        project = s.get(Project, project_id)
        if project is None:
            raise ProjectMissing
        if complete and project.stage == "CAST_APPROVED":
            new_stage = "VOICES_APPROVED"
        elif not complete and project.stage == "VOICES_APPROVED":
            new_stage = "CAST_APPROVED"
        if new_stage is not None:
            project.stage = new_stage
            project.updated_at = utcnow()
        stage = project.stage
    if new_stage is not None:
        ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": new_stage})
    return stage


def counts(lines: list[dict[str, Any]]) -> tuple[int, int, int]:
    """(approved, total, stale) over the lines that have text."""
    texted = [ln for ln in lines if ln["state"] != "no_dialogue"]
    return (
        sum(1 for ln in texted if ln["state"] == "approved"),
        len(texted),
        sum(1 for ln in texted if ln["state"] == "stale"),
    )


def voices_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

    story = require(ctx, project_id)
    model = current_voice_model(ctx)
    lines = build_lines(ctx, project_id)
    approved, total, stale = counts(lines)
    jobs = voice_jobs(ctx, project_id)
    return {
        "stage": project_stage(ctx, project_id),
        "voice_model": {
            "key": model,
            "label": slots.MODEL_LABELS[model],
            "model_id": slots.model_id_of(ctx, model),
        },
        "presets": [{"id": p.id, "label": p.label} for p in PRESETS[model]],
        "approved_count": approved,
        "total": total,
        "stale_count": stale,
        "characters": characters_body(ctx, project_id, story),
        "lines": lines,
        "job": job_body(jobs[0]) if jobs else None,
    }


# ---- generation requests -------------------------------------------------------------------


def _skip_reason(li: LineInput) -> str | None:
    if not slots.voice_usable(li.slot):
        return "no voice"
    if li.slot is not None and li.slot.mode == "recorded":
        return "recorded voice"
    return None


def plan_generation(
    ctx: AppContext, project_id: str, mode: str, wanted: list[str] | None
) -> tuple[list[str], list[dict[str, str]]]:
    """Scene ids to render (story order) and the lines skipped with a reason."""
    inputs = line_inputs(ctx, project_id)
    lines = {ln["scene_id"]: ln for ln in build_lines(ctx, project_id)}
    if mode == "lines":
        unknown = [w for w in (wanted or []) if w not in inputs]
        if unknown:
            raise VoiceError(404, "line not found")
        candidates = [sid for sid in inputs if sid in (wanted or [])]
    elif mode == "stale":
        candidates = [sid for sid, ln in lines.items() if ln["state"] == "stale"]
    else:
        candidates = [
            sid
            for sid, ln in lines.items()
            if ln["state"] in ("no_take", "failed", "no_voice")
            and not any(t["active"] for t in ln["takes"])
            and inputs[sid].text
        ]
    ids: list[str] = []
    skipped: list[dict[str, str]] = []
    for sid in candidates:
        li = inputs[sid]
        if not li.text:
            continue
        reason = _skip_reason(li)
        if reason is None:
            ids.append(sid)
        else:
            skipped.append({"scene_id": sid, "reason": reason})
    return ids, skipped


def enqueue_generation(
    ctx: AppContext, project_id: str, mode: str, wanted: list[str] | None
) -> Job:
    require(ctx, project_id)
    for job in voice_jobs(ctx, project_id):
        if job.status in ("queued", "running"):
            return job
    ids, skipped = plan_generation(ctx, project_id, mode, wanted)
    if not ids:
        raise VoiceError(409, "Nothing to generate.")
    return ctx.queue.enqueue(
        type=VOICE_JOB,
        project_id=project_id,
        payload={
            "stage": "voices",
            "mode": mode,
            "scene_ids": ids,
            "skipped": skipped,
            "total": len(ids),
        },
        heavy=True,
        mem_need_gb=ctx.settings.voice_mem_gb,
    )


def enqueue_preset_preview(ctx: AppContext, project_id: str, preset_id: str) -> Job:
    require(ctx, project_id)
    if preset_id not in slots.preset_ids(current_voice_model(ctx)):
        raise VoiceError(404, "preset not found")
    return ctx.queue.enqueue(
        type=VOICE_JOB,
        project_id=project_id,
        payload={"preview": preset_id},
        heavy=True,
        mem_need_gb=ctx.settings.voice_mem_gb,
    )
