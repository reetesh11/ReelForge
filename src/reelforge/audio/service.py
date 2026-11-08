"""Sound cue operations: the Sound screen body, cue edits, takes and mix settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.artifacts.store import ArtifactSpec
from reelforge.assembly.build import approved_shot_takes, build_edl, working_edl_path
from reelforge.assembly.edl import save_edl
from reelforge.audio import cues as cue_store
from reelforge.audio.backends import engine_status
from reelforge.audio.fit import FitError, fit_to_length
from reelforge.audio.state import (
    AUDIO_JOB,
    NEEDS_APPROVAL,
    OWNER_CUE,
    TAKE_KIND,
    AudioError,
    drop_slot,
    get_mix_settings,
    list_slots,
    put_mix_settings,
    set_picked,
)
from reelforge.audio.uploads import screen_audio
from reelforge.db.models import Artifact, Job, Project, StoryChange
from reelforge.story.audio import resolve_cue, story_timeline
from reelforge.story.schema import Cue, Story
from reelforge.story.staleness import ChangeRow, is_stale

if TYPE_CHECKING:
    from reelforge.context import AppContext

NOT_FOUND = "project not found"
CUE_NOT_FOUND = "cue not found"
TAKE_NOT_FOUND = "take not found"
END_TOLERANCE_S = 0.05
CUE_FIELDS = (
    "id", "kind", "start", "end", "duration", "prompt", "source",
    "gain_db", "fade_in_s", "fade_out_s", "duck",
)  # fmt: skip


def require(ctx: AppContext, project_id: str) -> Story:
    """The project's current story; 404 for an unknown project."""
    with ctx.session_factory() as s:
        if s.get(Project, project_id) is None:
            raise AudioError(404, NOT_FOUND)
    return cue_store.load_story(ctx, project_id)


def find_cue(story: Story, cue_id: str) -> Cue:
    cue = next((c for c in story.audio or [] if c.id == cue_id), None)
    if cue is None:
        raise AudioError(404, CUE_NOT_FOUND)
    return cue


# ---- times ---------------------------------------------------------------------------------


def timeline(ctx: AppContext, project_id: str, story: Story) -> dict[str, tuple[float, float]]:
    """Scene spans: the approved shot lengths when every scene has one, else the story's."""
    story_tl = story_timeline(story)
    takes = approved_shot_takes(ctx, project_id)
    if not takes or any(t is None for t in takes.values()):
        return story_tl
    out: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for scene in story.scenes:
        art = takes.get(scene.id)
        length = (float(art.duration_s) if art is not None and art.duration_s else None) or (
            story_tl[scene.id][1] - story_tl[scene.id][0]
        )
        out[scene.id] = (cursor, cursor + length)
        cursor += length
    return out


def cue_span(
    story: Story, cue: Cue, tl: dict[str, tuple[float, float]]
) -> tuple[float, float] | None:
    try:
        return resolve_cue(story, cue, tl)
    except KeyError:
        return None


# ---- takes ---------------------------------------------------------------------------------


def cue_takes(ctx: AppContext, project_id: str) -> dict[str, list[Artifact]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_CUE,
                Artifact.kind == TAKE_KIND,
            )
            .order_by(Artifact.take_no)
        )
        out: dict[str, list[Artifact]] = {}
        for r in rows:
            out.setdefault(r.owner_id, []).append(r)
    return out


def picked_takes(ctx: AppContext, project_id: str) -> dict[str, Artifact]:
    """The picked take of every cue that has one."""
    slots = list_slots(ctx, project_id)
    ids = [s.picked_artifact_id for s in slots.values() if s.picked_artifact_id]
    if not ids:
        return {}
    with ctx.session_factory() as s:
        arts = {a.id: a for a in s.scalars(select(Artifact).where(Artifact.id.in_(ids)))}
    return {
        cid: arts[slot.picked_artifact_id]
        for cid, slot in slots.items()
        if slot.picked_artifact_id in arts
    }


def _changes(ctx: AppContext, project_id: str) -> dict[str, list[ChangeRow]]:
    with ctx.session_factory() as s:
        rows = s.scalars(
            select(StoryChange).where(
                StoryChange.project_id == project_id, StoryChange.owner_type == OWNER_CUE
            )
        )
        out: dict[str, list[ChangeRow]] = {}
        for c in rows:
            out.setdefault(c.owner_id, []).append(
                ChangeRow(c.owner_type, c.owner_id, list(c.kinds), c.created_at)
            )
    return out


def licence_text(ctx: AppContext, take: Artifact | None) -> str:
    if take is None:
        return ""
    if take.model_key == "upload":
        note = str((take.params or {}).get("licence_note") or "").strip()
        return f"Your file: {note}" if note else "No licence note"
    try:
        return ctx.registry.get(take.model_key).license
    except KeyError:
        return ""


def _model_name(take: Artifact) -> str:
    return str((take.params or {}).get("model_id") or take.model_key)


# ---- the body ------------------------------------------------------------------------------


def _latest_jobs(ctx: AppContext, project_id: str) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for job in ctx.queue.list(project_id=project_id):  # newest first
        cid = job.payload.get("cue_id")
        if job.type == AUDIO_JOB and isinstance(cid, str) and cid not in latest:
            latest[cid] = job
    return latest


def audio_body(ctx: AppContext, project_id: str) -> dict[str, Any]:
    from reelforge.api.routes_jobs import job_body  # noqa: PLC0415

    story = require(ctx, project_id)
    tl = timeline(ctx, project_id, story)
    reel_end = max((end for _, end in tl.values()), default=0.0)
    takes = cue_takes(ctx, project_id)
    picked = picked_takes(ctx, project_id)
    changes = _changes(ctx, project_id)
    jobs = _latest_jobs(ctx, project_id)
    ok, message = engine_status(ctx)
    out_cues: list[dict[str, Any]] = []
    skipped = 0
    for order, cue in enumerate(story.audio or [], start=1):
        data = cue.model_dump(mode="json", exclude_none=True)
        item: dict[str, Any] = {k: data[k] for k in CUE_FIELDS if k in data}
        span = cue_span(story, cue, tl) or (0.0, 0.0)
        pick = picked.get(cue.id)
        stale = False
        if pick is not None:
            stale = is_stale(TAKE_KIND, pick.created_at, changes.get(cue.id, []))
        if cue.state == "suggested":
            state = "suggested"
        elif pick is None:
            state = "draft"
        else:
            state = "stale" if stale else "ready"
        if cue.kind != "silence" and pick is None:
            skipped += 1
        job = jobs.get(cue.id)
        item.update(
            order=order,
            state=state,
            start_s=span[0],
            end_s=span[1],
            duration_s=float(pick.duration_s)
            if pick is not None and pick.duration_s
            else span[1] - span[0],
            licence="" if cue.kind == "silence" else licence_text(ctx, pick),
            picked_take_id=pick.id if pick is not None else None,
            takes=[
                {
                    "id": t.id,
                    "take_no": t.take_no,
                    "seed": t.seed,
                    "model": _model_name(t),
                    "prompt": t.prompt,
                    "duration_s": float(t.duration_s or 0.0),
                    "url": f"/media/{t.id}",
                    "picked": pick is not None and t.id == pick.id,
                    "stale": is_stale(TAKE_KIND, t.created_at, changes.get(cue.id, [])),
                }
                for t in takes.get(cue.id, [])
            ],
            job=job_body(job)
            if job is not None and job.status in ("queued", "running", "failed")
            else None,
        )
        if pick is not None:
            name = str((pick.params or {}).get("file_name") or "")
            if name:
                item["file_name"] = name
        if span[1] > reel_end + END_TOLERANCE_S:
            item["flags"] = ["ends_after_reel"]
        out_cues.append(item)
    body: dict[str, Any] = {
        "engine": {"ok": ok, "message": message},
        "settings": get_mix_settings(ctx, project_id),
        "scenes": [{"id": sid, "start_s": a, "end_s": b} for sid, (a, b) in tl.items()],
        "cues": out_cues,
    }
    if story.music is not None and story.audio is None:
        body["legacy_music_hint"] = True
    if skipped:
        body["skipped_count"] = skipped
    return body


# ---- cue edits -----------------------------------------------------------------------------


def _write(ctx: AppContext, project_id: str, cues: list[Cue]) -> dict[str, Any]:
    cue_store.write_cues(ctx, project_id, cues)
    return audio_body(ctx, project_id)


def add_cue(ctx: AppContext, project_id: str, cue: Cue) -> dict[str, Any]:
    story = require(ctx, project_id)
    return _write(ctx, project_id, [*(story.audio or []), cue])


def update_cue(ctx: AppContext, project_id: str, cue_id: str, cue: Cue) -> dict[str, Any]:
    story = require(ctx, project_id)
    find_cue(story, cue_id)
    if cue.id != cue_id:
        raise AudioError(422, "A cue's id cannot be changed.")
    return _write(ctx, project_id, [cue if c.id == cue_id else c for c in story.audio or []])


def deactivate_takes(ctx: AppContext, project_id: str, cue_id: str) -> None:
    with ctx.session_factory.begin() as s:
        for row in s.scalars(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_CUE,
                Artifact.owner_id == cue_id,
            )
        ):
            row.is_active = False


def delete_cue(ctx: AppContext, project_id: str, cue_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    find_cue(story, cue_id)
    body = _write(ctx, project_id, [c for c in story.audio or [] if c.id != cue_id])
    drop_slot(ctx, project_id, cue_id)
    deactivate_takes(ctx, project_id, cue_id)
    return body


def move_cue(ctx: AppContext, project_id: str, cue_id: str, direction: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    find_cue(story, cue_id)
    cues = list(story.audio or [])
    i = next(n for n, c in enumerate(cues) if c.id == cue_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(cues):
        cues[i], cues[j] = cues[j], cues[i]
        return _write(ctx, project_id, cues)
    return audio_body(ctx, project_id)


def approve_cue(ctx: AppContext, project_id: str, cue_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    find_cue(story, cue_id)
    return _write(
        ctx,
        project_id,
        [c.model_copy(update={"state": None}) if c.id == cue_id else c for c in story.audio or []],
    )


def approve_all(ctx: AppContext, project_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    return _write(
        ctx, project_id, [c.model_copy(update={"state": None}) for c in story.audio or []]
    )


def dismiss_cue(ctx: AppContext, project_id: str, cue_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    cue = find_cue(story, cue_id)
    if cue.state != "suggested":
        raise AudioError(409, "Only a suggested cue can be dismissed.")
    return delete_cue(ctx, project_id, cue_id)


def select_take(ctx: AppContext, project_id: str, cue_id: str, take_id: str) -> dict[str, Any]:
    story = require(ctx, project_id)
    find_cue(story, cue_id)
    if take_id not in {t.id for t in cue_takes(ctx, project_id).get(cue_id, [])}:
        raise AudioError(404, TAKE_NOT_FOUND)
    set_picked(ctx, project_id, cue_id, take_id)
    return audio_body(ctx, project_id)


def settings_body(ctx: AppContext, project_id: str) -> dict[str, float]:
    require(ctx, project_id)
    return get_mix_settings(ctx, project_id)


def update_settings(ctx: AppContext, project_id: str, **values: float) -> dict[str, float]:
    require(ctx, project_id)
    return put_mix_settings(ctx, project_id, **values)


# ---- generating ----------------------------------------------------------------------------


def silence_text(cue_id: str) -> str:
    return f'Cue "{cue_id}": a silence cue has no audio.'


def empty_prompt_text(cue_id: str) -> str:
    return f'Cue "{cue_id}": prompt is empty.'


def file_cue_text(cue_id: str) -> str:
    return f'Cue "{cue_id}": this cue uses your own file.'


def _active_job(ctx: AppContext, project_id: str, cue_id: str) -> Job | None:
    for job in ctx.queue.list(project_id=project_id):
        if (
            job.type == AUDIO_JOB
            and job.payload.get("cue_id") == cue_id
            and job.status in ("queued", "running")
        ):
            return job
    return None


def generate(ctx: AppContext, project_id: str, cue_id: str) -> Job:
    """Queue one take of the cue (also Re-take); an unfinished job for the cue is returned."""
    story = require(ctx, project_id)
    cue = find_cue(story, cue_id)
    if cue.kind == "silence":
        raise AudioError(422, silence_text(cue_id))
    if cue.source == "file":
        raise AudioError(422, file_cue_text(cue_id))
    if cue.state == "suggested":
        raise AudioError(409, NEEDS_APPROVAL)
    if not (cue.prompt or "").strip():
        raise AudioError(422, empty_prompt_text(cue_id))
    existing = _active_job(ctx, project_id, cue_id)
    if existing is not None:
        return existing
    ok, message = engine_status(ctx)
    if not ok:
        raise AudioError(409, message)
    heavy = ctx.settings.backend != "mock"
    return ctx.queue.enqueue(
        type=AUDIO_JOB,
        project_id=project_id,
        payload={"cue_id": cue_id, "stage": "sound"},
        heavy=heavy,
        mem_need_gb=ctx.settings.audio_mem_gb if heavy else 0.0,
    )


# ---- own files -----------------------------------------------------------------------------


async def upload(
    ctx: AppContext,
    project_id: str,
    cue_id: str,
    data: bytes,
    file_name: str,
    licence_note: str,
) -> dict[str, Any]:
    """Fit the owner's file to the cue length and keep it as the cue's picked take."""
    story = require(ctx, project_id)
    cue = find_cue(story, cue_id)
    if cue.kind == "silence":
        raise AudioError(422, silence_text(cue_id))
    if cue.source != "file":
        raise AudioError(422, f'Cue "{cue_id}": this cue does not use your own file.')
    span = cue_span(story, cue, timeline(ctx, project_id, story))
    length = span[1] - span[0] if span is not None else 0.0
    if length <= 0:
        raise AudioError(422, f'Cue "{cue_id}" has no length.')
    clip = await screen_audio(ctx, data)
    fitted = clip.path.with_name(f"{clip.path.stem}.fit.wav")
    try:
        try:
            await fit_to_length(clip.path, fitted, length, channels=1)
        except FitError as exc:
            raise AudioError(415, str(exc)) from None
        name = file_name.strip() or f"{cue_id}.{clip.ext}"
        take = ctx.store.write(
            ArtifactSpec(
                project_id=project_id,
                owner_type=OWNER_CUE,
                owner_id=cue_id,
                kind=TAKE_KIND,
                subdir=f"audio/{cue_id}",
                prompt="uploaded file",
                seed=0,
                model_key="upload",
                model_revision="",
                adapter="upload",
                version="upload-1",
                params={
                    "source": "upload",
                    "file_name": name,
                    "licence_note": licence_note.strip(),
                },
                duration_s=length,
            ),
            fitted,
            ext="wav",
        )
    finally:
        clip.path.unlink(missing_ok=True)
        fitted.unlink(missing_ok=True)
    set_picked(ctx, project_id, cue_id, take.id)
    return audio_body(ctx, project_id)


# ---- preview of the full mix ---------------------------------------------------------------

SHOTS_LOCKED = "Approve the shots first."


def preview_mix(ctx: AppContext, project_id: str) -> Job:
    """Refresh the working EDL with the current cues and queue one preview (no export folder)."""
    from reelforge.assembly.state import AssemblyError  # noqa: PLC0415
    from reelforge.audio.build import refresh_audio  # noqa: PLC0415
    from reelforge.frames.service import stage_at_least  # noqa: PLC0415

    require(ctx, project_id)
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
    if project is None or not stage_at_least(project.stage, "SHOTS_APPROVED"):
        raise AudioError(409, SHOTS_LOCKED)
    try:
        if refresh_audio(ctx, project_id) is None:
            save_edl(build_edl(ctx, project_id), working_edl_path(ctx, project_id), full=True)
        return ctx.previews.enqueue_now(project_id)
    except AssemblyError as exc:
        raise AudioError(exc.status, exc.message) from None
