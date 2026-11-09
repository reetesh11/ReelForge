"""The cues in the EDL: absolute times from the shots, picked takes and the project's mix."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reelforge.assembly.build import working_edl_path
from reelforge.assembly.edl import Edl, EdlAudio, EdlMix, load_edl, save_edl
from reelforge.audio import cues as cue_store
from reelforge.audio import service
from reelforge.audio.state import AudioError, get_mix_settings
from reelforge.story.audio import KIND_DEFAULT_GAIN_DB, resolve_cue

if TYPE_CHECKING:
    from reelforge.context import AppContext

ROUND = 3


def edl_timeline(edl: Edl) -> dict[str, tuple[float, float]]:
    """Scene id to (start_s, end_s) on the reel, from the EDL's shots (transitions included)."""
    out: dict[str, tuple[float, float]] = {}
    for i, shot in enumerate(edl.video):
        start = edl.shot_start_s(i)
        out[shot.scene_id] = (start, start + (shot.out_s - shot.in_s))
    return out


def build_audio_section(
    ctx: AppContext, project_id: str, edl: Edl
) -> tuple[list[EdlAudio], EdlMix, int]:
    """(cues with absolute times, mix settings, cues left out for having no picked take)."""
    try:
        story = cue_store.load_story(ctx, project_id)
    except AudioError:
        return [], EdlMix(), 0
    cues = [c for c in story.audio or [] if c.state != "suggested"]
    if not cues:
        return [], EdlMix(), 0
    tl = edl_timeline(edl)
    picked = service.picked_takes(ctx, project_id)
    out: list[EdlAudio] = []
    skipped = 0
    for cue in cues:
        try:
            start, end = resolve_cue(story, cue, tl)
        except KeyError:
            continue
        silence = cue.kind == "silence"
        pick = None if silence else picked.get(cue.id)
        if not silence and pick is None:
            skipped += 1
            continue
        out.append(
            EdlAudio(
                cue_id=cue.id,
                kind=cue.kind,  # type: ignore[arg-type]
                artifact=pick.id if pick is not None else None,
                start_s=round(start, ROUND),
                end_s=round(end, ROUND),
                gain_db=0.0
                if silence
                else (
                    cue.gain_db
                    if cue.gain_db is not None
                    else KIND_DEFAULT_GAIN_DB.get(cue.kind, 0.0)
                ),
                fade_in_s=cue.fade_in_s or 0.0,
                fade_out_s=cue.fade_out_s or 0.0,
                duck=bool(cue.duck) and cue.kind == "music",
            )
        )
    mix = EdlMix(**get_mix_settings(ctx, project_id)) if out else EdlMix()
    return out, mix, skipped


def refresh_audio(ctx: AppContext, project_id: str) -> Edl | None:
    """Replace the working EDL's `audio` and `mix` with the current cues; None without an EDL."""
    path = working_edl_path(ctx, project_id)
    if not path.is_file():
        return None
    edl = load_edl(path)
    cues, mix, _ = build_audio_section(ctx, project_id, edl)
    edl = edl.model_copy(update={"audio": cues, "mix": mix})
    save_edl(edl, path, full=True)
    return edl
