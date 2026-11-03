"""Cast operations: approve, reopen, use from library, upload, stage and API item assembly."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast import state
from reelforge.db.models import (
    Approval,
    Artifact,
    CastSlot,
    Character,
    Job,
    Project,
    ProjectCharacter,
    utcnow,
)
from reelforge.library import service as library
from reelforge.voice import slots as voice_slots

if TYPE_CHECKING:
    from reelforge.context import AppContext

ACTIVE = ("queued", "running")
RAW_NOTE = "Using your look text as written."
UPLOAD_MODEL_KEY = "upload"


class ProjectMissing(Exception):
    pass


class StageLocked(Exception):
    pass


class UnknownCharacter(Exception):
    pass


class UnknownCandidate(Exception):
    pass


class NoMasterImage(Exception):
    pass


def require(ctx: AppContext, project_id: str, key: str | None = None) -> state.StoryCast:
    """Project exists, story approved, and `key` (when given) is a story character."""
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None:
        raise ProjectMissing(project_id)
    if project.stage == "DRAFT":
        raise StageLocked(project_id)
    story = state.load_story_cast(ctx, project_id)
    if key is not None and key not in story.characters:
        raise UnknownCharacter(key)
    return story


def project_stage(ctx: AppContext, project_id: str) -> str:
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
        return project.stage if project is not None else "DRAFT"


def approved_count(story: state.StoryCast, slots: dict[str, CastSlot]) -> int:
    return sum(
        1
        for key in story.characters
        if key in slots and slots[key].approved_artifact_id is not None
    )


def recompute_stage(ctx: AppContext, project_id: str) -> str:
    """CAST_APPROVED iff every story character is approved; publishes stage.changed.

    An incomplete cast also demotes VOICES_APPROVED.
    """
    story = state.load_story_cast(ctx, project_id)
    slots = state.list_slots(ctx, project_id)
    complete = bool(story.characters) and approved_count(story, slots) == len(story.characters)
    new_stage: str | None = None
    with ctx.session_factory.begin() as s:
        project = s.get(Project, project_id)
        if project is None:
            raise ProjectMissing(project_id)
        if complete and project.stage == "STORY_APPROVED":
            new_stage = "CAST_APPROVED"
        elif not complete and project.stage in ("CAST_APPROVED", "VOICES_APPROVED"):
            new_stage = "STORY_APPROVED"
        if new_stage is not None:
            project.stage = new_stage
            project.updated_at = utcnow()
        stage = project.stage
    if new_stage is not None:
        ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": new_stage})
    return stage


def _sidecar(ctx: AppContext, artifact: Artifact) -> dict[str, Any]:
    path = ctx.store.absolute_path(artifact).with_suffix(".json")
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}


def linked_character(ctx: AppContext, project_id: str, key: str) -> Character | None:
    with ctx.session_factory() as s:
        link = s.get(ProjectCharacter, (project_id, key))
        return s.get(Character, link.character_id) if link is not None else None


def _link(ctx: AppContext, project_id: str, key: str, character_id: str) -> None:
    with ctx.session_factory.begin() as s:
        link = s.get(ProjectCharacter, (project_id, key))
        if link is None:
            s.add(ProjectCharacter(project_id=project_id, story_key=key, character_id=character_id))
        else:
            link.character_id = character_id


def ensure_own_character(ctx: AppContext, project_id: str, key: str) -> CastSlot | None:
    """A library-sourced character never writes to its library original: make a linked copy."""
    slot = state.get_slot(ctx, project_id, key)
    if slot is None or slot.origin != "reused":
        return slot
    original = linked_character(ctx, project_id, key)
    if original is None:
        return state.update_slot(ctx, project_id, key, origin="saved")
    variant = library.make_variant(ctx, original.id)
    _link(ctx, project_id, key, variant.id)
    return state.update_slot(ctx, project_id, key, origin="saved", variant_of_id=original.id)


def apply_look_text(ctx: AppContext, project_id: str, key: str, text: str) -> None:
    """Store an edited bible line (source `user`); a library-sourced line makes a variant first."""
    text = text.strip()
    slot = state.get_slot(ctx, project_id, key)
    if not text or (slot is not None and slot.bible_line == text):
        return
    if slot is not None and slot.origin == "reused":
        ensure_own_character(ctx, project_id, key)
    state.update_slot(ctx, project_id, key, bible_line=text, bible_source="user")


def _write_master(
    ctx: AppContext,
    project_id: str,
    key: str,
    *,
    data: bytes,
    ext: str,
    prompt: str,
    seed: int,
    model_key: str,
    model_id: str,
    revision: str,
    adapter: str,
    version: str,
    params: dict[str, Any],
    license_: str,
    license_url: str,
    inputs: list[str],
    width: int | None,
    height: int | None,
) -> Artifact:
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=state.OWNER_TYPE,
        owner_id=key,
        kind=state.MASTER_KIND,
        subdir=f"cast/{key}/master",
        prompt=prompt,
        seed=seed,
        model_key=model_key,
        model_id=model_id,
        model_revision=revision,
        adapter=adapter,
        version=version,
        params=params,
        input_artifact_ids=inputs,
        width=width,
        height=height,
        license=license_,
        license_url=license_url,
    )
    return ctx.store.write(spec, data, ext=ext)


def _finish_approval(
    ctx: AppContext, project_id: str, key: str, master: Artifact, **slot_values: Any
) -> None:
    state.update_slot(ctx, project_id, key, approved_artifact_id=master.id, **slot_values)
    with ctx.session_factory.begin() as s:
        s.add(
            Approval(
                project_id=project_id,
                stage="cast",
                owner_type=state.OWNER_TYPE,
                owner_id=key,
                artifact_id=master.id,
            )
        )
    recompute_stage(ctx, project_id)


def approve(
    ctx: AppContext, project_id: str, key: str, candidate_id: str, story: state.StoryCast
) -> None:
    slot = state.get_slot(ctx, project_id, key)
    if slot is None or candidate_id not in (slot.candidate_ids or []):
        raise UnknownCandidate(candidate_id)
    if slot.approved_candidate_id == candidate_id and slot.approved_artifact_id:
        return  # idempotent
    with ctx.session_factory() as s:
        candidate = s.get(Artifact, candidate_id)
    if candidate is None:
        raise UnknownCandidate(candidate_id)
    slot = ensure_own_character(ctx, project_id, key) or slot
    side = _sidecar(ctx, candidate)
    path = ctx.store.absolute_path(candidate)
    master = _write_master(
        ctx,
        project_id,
        key,
        data=path.read_bytes(),
        ext=path.suffix.lstrip("."),
        prompt=candidate.prompt,
        seed=candidate.seed,
        model_key=candidate.model_key,
        model_id=str(side.get("model_id") or ""),
        revision=str(side.get("model_revision") or ""),
        adapter=str(side.get("adapter") or ""),
        version=candidate.version,
        params=dict(candidate.params or {}),
        license_=str(side.get("license") or ""),
        license_url=str(side.get("license_url") or ""),
        inputs=[candidate.id],
        width=candidate.width,
        height=candidate.height,
    )
    char = story.characters[key]
    linked = linked_character(ctx, project_id, key)
    saved = library.save_from_artifact(
        ctx,
        artifact=master,
        name=char.name,
        aliases=char.aliases,
        look_text=slot.bible_line or char.look,
        seed=candidate.seed,
        voice_reference=slot.voice_reference,
        existing_id=linked.id if linked is not None else None,
    )
    _link(ctx, project_id, key, saved.id)
    if voice_slots.get_slot(ctx, project_id, key) is not None:
        voice_slots.sync_to_library(ctx, project_id, key, saved.id)
    _finish_approval(
        ctx, project_id, key, master,
        approved_candidate_id=candidate_id, seed=candidate.seed, origin="saved",
    )  # fmt: skip


def reopen(ctx: AppContext, project_id: str, key: str) -> None:
    if state.get_slot(ctx, project_id, key) is not None:
        state.update_slot(
            ctx, project_id, key, approved_artifact_id=None, approved_candidate_id=None
        )
    recompute_stage(ctx, project_id)


def use_library(ctx: AppContext, project_id: str, key: str, character_id: str) -> None:
    ch = library.get(ctx, character_id)
    if ch is None:
        raise UnknownCharacter(character_id)
    found = library.master_file(ctx, ch)
    if found is None:
        raise NoMasterImage(character_id)
    path = found[0]
    revision = ""
    if ch.model_key and ch.model_key in ctx.registry.keys():
        revision = ctx.registry.get(ch.model_key).revision
    master = _write_master(
        ctx,
        project_id,
        key,
        data=path.read_bytes(),
        ext=path.suffix.lstrip("."),
        prompt=ch.look_text,
        seed=ch.seed or 0,
        model_key=ch.model_key or UPLOAD_MODEL_KEY,
        model_id=ch.model_id or "",
        revision=revision,
        adapter="library",
        version="library-1",
        params={},
        license_=ch.license,
        license_url=ch.license_url,
        inputs=[],
        width=None,
        height=None,
    )
    _link(ctx, project_id, key, ch.id)
    voice_slots.adopt_from_library(ctx, project_id, key, ch.id)
    _finish_approval(
        ctx, project_id, key, master,
        bible_line=ch.look_text, bible_source="user", seed=ch.seed,
        voice_reference=ch.voice_reference, origin="reused", variant_of_id=None,
        approved_candidate_id=None,
    )  # fmt: skip


def store_upload(
    ctx: AppContext, project_id: str, key: str, data: bytes, ext: str, width: int, height: int
) -> None:
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=state.OWNER_TYPE,
        owner_id=key,
        kind=state.UPLOAD_KIND,
        subdir="uploads",
        prompt="uploaded image",
        seed=0,
        model_key=UPLOAD_MODEL_KEY,
        model_revision="",
        adapter="upload",
        version="upload-1",
        width=width,
        height=height,
    )
    artifact = ctx.store.write(spec, data, ext=ext)
    state.update_slot(ctx, project_id, key, candidate_ids=[artifact.id])


# ---- API item assembly ---------------------------------------------------------------------


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def latest_jobs(ctx: AppContext, project_id: str) -> dict[str, Job]:
    latest: dict[str, Job] = {}
    for job in ctx.queue.list(project_id=project_id):  # newest first
        if job.type == state.GENERATE_JOB:
            latest.setdefault(str(job.payload.get("key", "")), job)
    return latest


def active_job(ctx: AppContext, project_id: str, key: str) -> Job | None:
    for job in ctx.queue.list(project_id=project_id):
        if (
            job.type == state.GENERATE_JOB
            and job.payload.get("key") == key
            and job.status in ACTIVE
        ):
            return job
    return None


def _progress(job: Job) -> dict[str, Any]:
    result = job.result or {}
    total = int(result.get("total") or job.payload.get("total") or state.CANDIDATES_PER_RUN)
    elapsed = result.get("elapsed_s")
    started = _aware(job.started_at)
    if job.status == "running" and started is not None:
        elapsed = (datetime.now(UTC) - started).total_seconds()
    return {
        "completed": int(result.get("completed") or 0),
        "total": total,
        "elapsed_s": round(float(elapsed or 0.0), 1),
        "message": job.message or "",
    }


def build_item(
    ctx: AppContext,
    char: state.StoryCharacter,
    slot: CastSlot | None,
    job: Job | None,
    project_id: str,
) -> dict[str, Any]:
    cands = state.candidates(ctx, slot)
    approved = slot is not None and slot.approved_artifact_id is not None
    item: dict[str, Any] = {
        "key": char.key,
        "name": char.name,
        "aliases": char.aliases,
        "look": char.look,
        "bible_line": slot.bible_line if slot is not None else "",
        "bible_source": slot.bible_source if slot is not None else "",
        "candidates": cands,
        "approved": approved,
        "voice_reference": slot.voice_reference if slot is not None else "",
    }
    if slot is not None and slot.bible_source == "raw":
        item["note"] = RAW_NOTE
    status = "empty"
    if cands:
        status = "ready"
    if job is not None:
        item["job_id"] = job.id
        progress = _progress(job)
        item["progress"] = progress
        if job.status in ACTIVE:
            status = "generating"
        elif job.status == "failed" and not (cands and cands[0]["kind"] == "upload"):
            status = "failed"
            item["error"] = job.error or "Couldn't generate images."
        elif job.status == "cancelled" and progress["completed"] < progress["total"]:
            status = "stopped"
    if approved and status not in ("generating", "failed"):
        status = "approved"
    item["state"] = status
    if slot is not None and slot.approved_artifact_id:
        with ctx.session_factory() as s:
            master = s.get(Artifact, slot.approved_artifact_id)
        if master is not None:
            item["master_artifact_id"] = master.id
            item["master_sha256"] = master.sha256
    if slot is not None and slot.seed is not None:
        item["seed"] = slot.seed
    linked = linked_character(ctx, project_id, char.key) if slot is not None else None
    if linked is not None and approved:
        item["library_character_id"] = linked.id
    if slot is not None and slot.variant_of_id:
        item["variant_of_library_id"] = slot.variant_of_id
    return item
