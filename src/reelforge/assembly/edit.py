"""Timeline and caption edits applied to the working EDL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reelforge.assembly import ffmpeg
from reelforge.assembly.build import working_edl_path
from reelforge.assembly.edl import CAPTION_STYLES, Edl, load_edl, save_edl
from reelforge.assembly.state import AssemblyError
from reelforge.db.models import Artifact
from reelforge.shots import service as shots_service

if TYPE_CHECKING:
    from reelforge.context import AppContext

MIN_SHOT_S = 0.5
MAX_FADE_S = 0.5
TRIMMED = "Dialogue was trimmed to fit."
FADE_SHORTENED = "Crossfade shortened to fit"
NOT_BUILT = "edl not built"
EPS = 1e-6


def load_working(ctx: AppContext, project_id: str) -> Edl:
    path = working_edl_path(ctx, project_id)
    if not path.is_file():
        raise AssemblyError(404, NOT_BUILT)
    return load_edl(path)


def _number(op: dict[str, Any], name: str) -> float:
    value = op.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AssemblyError(422, f"{name} must be a number.")
    return float(value)


def _text(op: dict[str, Any], name: str) -> str:
    value = op.get(name)
    if not isinstance(value, str):
        raise AssemblyError(422, f"{name} is required.")
    return value


def _index(edl: Edl, scene_id: str) -> int:
    for i, shot in enumerate(edl.video):
        if shot.scene_id == scene_id:
            return i
    raise AssemblyError(404, "scene not found")


def _fit_dialogue(edl: Edl) -> bool:
    """Cut dialogue (and its caption) that runs past the end of the reel; True when changed."""
    total = edl.total_duration_s
    changed = False
    dialogue = []
    drop: set[str] = set()
    for clip in edl.dialogue:
        if clip.offset_s + clip.duration_s <= total + EPS:
            dialogue.append(clip)
            continue
        changed = True
        room = round(total - clip.offset_s, 2)
        if room <= 0:
            drop.add(clip.scene_id)
            continue
        dialogue.append(clip.model_copy(update={"duration_s": room}))
    captions = []
    for cap in edl.captions:
        if cap.scene_id in drop:
            continue
        clip = next((d for d in dialogue if d.scene_id == cap.scene_id), None)
        if clip is not None and cap.end_s > clip.offset_s + clip.duration_s + EPS:
            cap = cap.model_copy(update={"end_s": round(clip.offset_s + clip.duration_s, 2)})
        captions.append(cap)
    for n, cap in enumerate(captions, start=1):
        captions[n - 1] = cap.model_copy(update={"line_no": n})
    edl.dialogue = dialogue
    edl.captions = captions
    return changed


def _reorder(edl: Edl, op: dict[str, Any]) -> None:
    ids = op.get("scene_ids")
    current = [s.scene_id for s in edl.video]
    if not isinstance(ids, list) or sorted(map(str, ids)) != sorted(current):
        raise AssemblyError(422, "List every shot exactly once to reorder.")
    ids = [str(i) for i in ids]
    old_start = {s.scene_id: edl.shot_start_s(i) for i, s in enumerate(edl.video)}
    by_id = {s.scene_id: s for s in edl.video}
    edl.video = [by_id[i] for i in ids]
    new_start = {s.scene_id: edl.shot_start_s(i) for i, s in enumerate(edl.video)}
    rank = {sid: n for n, sid in enumerate(ids)}
    for clip in edl.dialogue:
        shift = new_start[clip.scene_id] - old_start[clip.scene_id]
        clip.offset_s = round(max(0.0, clip.offset_s + shift), 3)
    for cap in edl.captions:
        shift = new_start[cap.scene_id] - old_start[cap.scene_id]
        cap.start_s = round(max(0.0, cap.start_s + shift), 3)
        cap.end_s = round(max(0.0, cap.end_s + shift), 3)
    edl.dialogue.sort(key=lambda d: rank[d.scene_id])
    edl.captions.sort(key=lambda c: rank[c.scene_id])
    for n, cap in enumerate(edl.captions, start=1):
        cap.line_no = n


def _trim(edl: Edl, op: dict[str, Any]) -> None:
    shot = edl.video[_index(edl, _text(op, "scene_id"))]
    start, end = round(_number(op, "in_s"), 2), round(_number(op, "out_s"), 2)
    if start < 0 or end > shot.source_duration_s + EPS or start >= end:
        raise AssemblyError(422, "Trim points must lie inside the shot.")
    if end - start < MIN_SHOT_S - EPS:
        raise AssemblyError(422, "A shot must be at least 0.5 s long.")
    shot.in_s, shot.out_s = start, end


def _swap(ctx: AppContext, project_id: str, edl: Edl, op: dict[str, Any]) -> None:
    scene_id = _text(op, "scene_id")
    shot = edl.video[_index(edl, scene_id)]
    take_id = _text(op, "take_id")
    takes = shots_service.shot_takes(ctx, project_id).get(scene_id, [])
    take = next((t for t in takes if t.id == take_id), None)
    if take is None:
        raise AssemblyError(404, "take not found")
    length = _take_length(ctx, take)
    shot.artifact = take.id
    shot.source_duration_s = length
    shot.in_s, shot.out_s = 0.0, length


def _take_length(ctx: AppContext, take: Artifact) -> float:
    try:
        return round(ffmpeg.media_duration(ctx.store.absolute_path(take), "video"), 2)
    except (ValueError, OSError):
        return round(float(take.duration_s or 0.0), 2)


def _transition(edl: Edl, op: dict[str, Any], notes: list[str]) -> None:
    index = _index(edl, _text(op, "scene_id"))
    seconds = _number(op, "seconds")
    if seconds < 0 or seconds > MAX_FADE_S + EPS:
        raise AssemblyError(422, "A crossfade is 0 to 0.5 s.")
    seconds = round(seconds, 2)
    if index > 0:
        shorter = min(
            edl.video[index - 1].out_s - edl.video[index - 1].in_s,
            edl.video[index].out_s - edl.video[index].in_s,
        )
        cap = round(shorter / 2, 2)
        if seconds > cap + EPS:
            seconds = cap
            notes.append(FADE_SHORTENED)
    edl.video[index].transition_in_s = seconds if index > 0 else 0.0


def _nudge(edl: Edl, op: dict[str, Any]) -> None:
    scene_id = _text(op, "scene_id")
    offset = _number(op, "offset_s")
    if offset < 0 or offset > edl.total_duration_s + EPS:
        raise AssemblyError(422, "Dialogue cannot start before 0 or after the end of the reel.")
    clip = next((d for d in edl.dialogue if d.scene_id == scene_id), None)
    if clip is None:
        raise AssemblyError(404, "dialogue not found")
    clip.offset_s = round(offset, 3)
    for cap in edl.captions:
        if cap.scene_id == scene_id:
            cap.start_s = clip.offset_s
            cap.end_s = round(clip.offset_s + clip.duration_s, 3)


def _caption_text(edl: Edl, op: dict[str, Any]) -> None:
    scene_id = _text(op, "scene_id")
    text = _text(op, "text")
    cap = next((c for c in edl.captions if c.scene_id == scene_id), None)
    if cap is None:
        raise AssemblyError(404, "caption not found")
    cap.text = text


def _caption_style(edl: Edl, op: dict[str, Any]) -> None:
    style = op.get("style")
    if style not in CAPTION_STYLES:
        raise AssemblyError(422, "Unknown caption style.")
    edl.caption_style = str(style)


def apply_edit(ctx: AppContext, project_id: str, op: dict[str, Any]) -> tuple[Edl, list[str]]:
    """Apply one edit to the working EDL, save it and return it with any notes."""
    edl = load_working(ctx, project_id).model_copy(deep=True)
    notes: list[str] = []
    name = op.get("op")
    if name == "reorder":
        _reorder(edl, op)
    elif name == "trim":
        _trim(edl, op)
    elif name == "swap_take":
        _swap(ctx, project_id, edl, op)
    elif name == "set_transition":
        _transition(edl, op, notes)
    elif name == "nudge_dialogue":
        _nudge(edl, op)
    elif name == "set_caption_text":
        _caption_text(edl, op)
    elif name == "set_caption_style":
        _caption_style(edl, op)
    else:
        raise AssemblyError(422, "Unknown edit.")
    if name not in ("set_caption_text", "set_caption_style") and _fit_dialogue(edl):
        notes.append(TRIMMED)
    edl = Edl.model_validate(edl.model_dump())
    save_edl(edl, working_edl_path(ctx, project_id))
    return edl, notes
