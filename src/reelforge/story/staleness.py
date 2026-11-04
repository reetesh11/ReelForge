"""Semantic diff between two stories, and the stale computation over artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reelforge.story.audio import resolve_cue, story_timeline
from reelforge.story.schema import Cue, Story

TOP_LEVEL_FIELDS = (
    "version",
    "language",
    "style",
    "aspect",
    "fps",
    "target_seconds",
    "brand_kit",
    "product",
    "music",
    "captions",
)
CUE_TAKE_FIELDS = ("kind", "start", "end", "duration", "prompt", "source")
CUE_MIX_FIELDS = ("gain_db", "fade_in_s", "fade_out_s", "duck")
LINE_KINDS = ["voice_take", "shot"]
ALL = ["*"]


@dataclass(frozen=True)
class Affected:
    owner_type: str
    owner_id: str
    kinds: list[str]


def _scene_fields(scene: Any) -> dict[str, Any]:
    data: dict[str, Any] = scene.model_dump()
    data.pop("suggested", None)
    return data


def _cue_length(story: Story, cue: Cue) -> float | None:
    try:
        start, end = resolve_cue(story, cue, story_timeline(story))
    except KeyError:
        return None
    return end - start


def _diff_cues(old: Story, new: Story) -> list[Affected]:
    """Cue changes: a take-affecting edit stales the take, a mix-only edit stales the mix."""
    old_cues = {c.id: c for c in old.audio or []}
    new_cues = {c.id: c for c in new.audio or []}
    out: list[Affected] = []
    for cid in list(new_cues) + [i for i in old_cues if i not in new_cues]:
        a, b = old_cues.get(cid), new_cues.get(cid)
        if a is None or b is None:
            out.append(Affected("audio_cue", cid, list(ALL)))
            continue
        take = any(getattr(a, f) != getattr(b, f) for f in CUE_TAKE_FIELDS)
        if not take:
            la, lb = _cue_length(old, a), _cue_length(new, b)
            take = la is None or lb is None or abs(la - lb) > 1e-6
        if take:
            out.append(Affected("audio_cue", cid, ["audio_take"]))
        elif any(getattr(a, f) != getattr(b, f) for f in CUE_MIX_FIELDS):
            out.append(Affected("audio_cue", cid, ["audio_mix"]))
    return out


def diff_stories(old: Story, new: Story) -> list[Affected]:
    """Which scenes, characters and cues an edit touches; rows are matched by id/key."""
    return _diff_scenes(old, new) + _diff_cues(old, new)


def _diff_scenes(old: Story, new: Story) -> list[Affected]:
    old_scenes = {s.id: s for s in old.scenes}
    new_scenes = {s.id: s for s in new.scenes}
    scene_ids = list(new_scenes) + [i for i in old_scenes if i not in new_scenes]
    char_keys = list(new.characters) + [k for k in old.characters if k not in new.characters]

    # once a story has cues, the old `music` note is ignored everywhere
    fields = TOP_LEVEL_FIELDS
    if old.audio is not None or new.audio is not None:
        fields = tuple(f for f in fields if f != "music")
    if any(getattr(old, f) != getattr(new, f) for f in fields):
        return [Affected("scene", i, list(ALL)) for i in scene_ids] + [
            Affected("character", k, list(ALL)) for k in char_keys
        ]

    out: list[Affected] = []
    for sid in scene_ids:
        a, b = old_scenes.get(sid), new_scenes.get(sid)
        if a is None or b is None:
            out.append(Affected("scene", sid, list(ALL)))
            continue
        fa, fb = _scene_fields(a), _scene_fields(b)
        changed = {k for k in fa if fa[k] != fb[k]}
        if not changed:
            continue
        kinds = list(LINE_KINDS) if changed <= {"line", "emotion"} else list(ALL)
        out.append(Affected("scene", sid, kinds))
    for key in char_keys:
        ca, cb = old.characters.get(key), new.characters.get(key)
        if ca != cb:
            out.append(Affected("character", key, list(ALL)))
    return out


@dataclass(frozen=True)
class ChangeRow:
    owner_type: str
    owner_id: str
    kinds: list[str]
    created_at: datetime


def is_stale(kind: str, created_at: datetime, changes: list[ChangeRow]) -> bool:
    return any(c.created_at > created_at and ("*" in c.kinds or kind in c.kinds) for c in changes)
