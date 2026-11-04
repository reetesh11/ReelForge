"""Build the EDL from the approved shot takes, voice takes and story lines."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from reelforge.assembly import ffmpeg
from reelforge.assembly.edl import Edl, EdlCaption, EdlDialogue, EdlShot
from reelforge.assembly.state import AssemblyError
from reelforge.db.models import Artifact, Project
from reelforge.shots.state import get_slot
from reelforge.voice import service as voice_service

if TYPE_CHECKING:
    from reelforge.context import AppContext

NOT_APPROVED = "Approve all shots before exporting."
NOT_FOUND = "project not found"


def project_row(ctx: AppContext, project_id: str) -> Project:
    with ctx.session_factory() as s:
        project = s.get(Project, project_id)
        if project is not None:
            s.expunge(project)
    if project is None:
        raise AssemblyError(404, NOT_FOUND)
    return project


def assembly_dir(ctx: AppContext, project_id: str) -> Path:
    return ctx.settings.data_root / project_row(ctx, project_id).data_dir / "assembly"


def working_edl_path(ctx: AppContext, project_id: str) -> Path:
    return assembly_dir(ctx, project_id) / "edl.json"


def _length(path: Path, art: Artifact, kind: str) -> float:
    try:
        return ffmpeg.media_duration(path, kind)
    except (ValueError, OSError):
        return float(art.duration_s or 0.0)


def approved_shot_takes(ctx: AppContext, project_id: str) -> dict[str, Artifact | None]:
    """The approved shot take of each scene in story order (None when there is none)."""
    story = voice_service.load_story(ctx, project_id)
    out: dict[str, Artifact | None] = {}
    if story is None:
        return out
    with ctx.session_factory() as s:
        for scene in story.scenes:
            slot = get_slot(ctx, project_id, scene.id)
            art = (
                s.get(Artifact, slot.approved_artifact_id)
                if slot is not None and slot.approved_artifact_id
                else None
            )
            out[scene.id] = art
    return out


def blocked_reason(ctx: AppContext, project_id: str) -> str | None:
    takes = approved_shot_takes(ctx, project_id)
    if not takes or any(t is None for t in takes.values()):
        return NOT_APPROVED
    return None


def build_edl(ctx: AppContext, project_id: str) -> Edl:
    takes = approved_shot_takes(ctx, project_id)
    if not takes or any(t is None for t in takes.values()):
        raise AssemblyError(409, NOT_APPROVED)
    video: list[EdlShot] = []
    for sid, art in takes.items():
        if art is None:
            continue
        length = round(_length(ctx.store.absolute_path(art), art, "video"), 2)
        video.append(
            EdlShot(
                scene_id=sid,
                artifact=art.id,
                source_duration_s=length,
                in_s=0.0,
                out_s=length,
                transition_in_s=0.0,
            )
        )
    edl = Edl(project_id=project_id, video=video, dialogue=[], captions=[])
    total = edl.total_duration_s
    inputs = voice_service.line_inputs(ctx, project_id)
    dialogue: list[EdlDialogue] = []
    captions: list[EdlCaption] = []
    with ctx.session_factory() as s:
        for index, shot in enumerate(video):
            li = inputs.get(shot.scene_id)
            if li is None or not li.text or not li.approved_artifact_id:
                continue
            take = s.get(Artifact, li.approved_artifact_id)
            if take is None:
                continue
            offset = round(edl.shot_start_s(index), 2)
            length = round(_length(ctx.store.absolute_path(take), take, "audio"), 2)
            duration = round(min(length, max(total - offset, 0.0)), 2)
            if duration <= 0:
                continue
            dialogue.append(
                EdlDialogue(
                    scene_id=shot.scene_id, artifact=take.id, offset_s=offset, duration_s=duration
                )
            )
            captions.append(
                EdlCaption(
                    scene_id=shot.scene_id,
                    speaker=li.speaker_name,
                    line_no=len(captions) + 1,
                    text=li.text,
                    start_s=offset,
                    end_s=round(offset + duration, 2),
                )
            )
    return edl.model_copy(update={"dialogue": dialogue, "captions": captions})
