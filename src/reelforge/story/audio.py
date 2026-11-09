"""Cue timing on the story timeline: scene positions, resolved cue spans and cue checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reelforge.story.schema import Cue, CueTime, Story

KIND_DEFAULT_GAIN_DB = {"music": -12.0, "sfx": -6.0, "ambience": -18.0}
EPS = 1e-6


def story_timeline(story: Story) -> dict[str, tuple[float, float]]:
    """Scene id to (start_s, end_s); a scene without a duration takes its share of the target."""
    share = story.target_seconds / len(story.scenes)
    out: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for scene in story.scenes:
        length = scene.duration if scene.duration is not None else share
        out[scene.id] = (cursor, cursor + length)
        cursor += length
    return out


def _time(point: CueTime, timeline: dict[str, tuple[float, float]]) -> float:
    start, end = timeline[point.scene]
    return (end if point.at == "scene_end" else start) + point.offset


def resolve_cue(
    story: Story, cue: Cue, timeline: dict[str, tuple[float, float]] | None = None
) -> tuple[float, float]:
    """Absolute (start_s, end_s) of a cue; raises KeyError for an unknown scene."""
    tl = timeline if timeline is not None else story_timeline(story)
    start = _time(cue.start, tl)
    if cue.duration is not None:
        return start, start + cue.duration
    if cue.end is not None:
        return start, _time(cue.end, tl)
    return start, start


def cue_issues(story: Story) -> list[tuple[str, str]]:
    """Every problem in the story's cue list as (path, message)."""
    issues: list[tuple[str, str]] = []
    timeline = story_timeline(story)
    seen: set[str] = set()
    for i, cue in enumerate(story.audio or []):
        path = f"audio[{i}]"
        name = f'Cue "{cue.id}"'

        def bad(text: str, path: str = path, name: str = name) -> None:
            issues.append((path, f"{name}: {text}"))

        if cue.id in seen:
            bad("id is used more than once.")
        seen.add(cue.id)
        if cue.kind not in ("music", "sfx", "ambience", "silence"):
            bad(f'unknown kind "{cue.kind}"; use music, sfx, ambience or silence.')
        unknown = {
            p.scene for p in (cue.start, cue.end) if p is not None and p.scene not in timeline
        }
        for scene in sorted(unknown):
            bad(f'unknown scene "{scene}".')
        if (cue.end is None) == (cue.duration is None):
            bad("give either end or duration.")
        if unknown:
            continue
        start, end = resolve_cue(story, cue, timeline)
        if start < -EPS:
            bad("start must not be negative.")
        if (cue.end is None) == (cue.duration is None):
            continue
        if cue.duration is not None and cue.duration < -EPS:
            bad("duration must not be negative.")
        elif cue.end is not None and end < -EPS:
            bad("end must not be negative.")
        elif start >= -EPS:
            if end < start - EPS:
                bad(f"end ({end:.1f} s) is before start ({start:.1f} s).")
            elif end <= start + EPS:
                bad(f"end ({end:.1f} s) is not after start ({start:.1f} s).")
    return issues
