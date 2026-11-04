"""Semantic diff between two stories, and the stale computation over artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reelforge.story.schema import Story

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


def diff_stories(old: Story, new: Story) -> list[Affected]:
    """Which scenes and characters an edit touches; rows are matched by id/key."""
    old_scenes = {s.id: s for s in old.scenes}
    new_scenes = {s.id: s for s in new.scenes}
    scene_ids = list(new_scenes) + [i for i in old_scenes if i not in new_scenes]
    char_keys = list(new.characters) + [k for k in old.characters if k not in new.characters]

    if any(getattr(old, f) != getattr(new, f) for f in TOP_LEVEL_FIELDS):
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
