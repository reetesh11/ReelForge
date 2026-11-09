"""Read and write the cue list in story.yaml (every edit is a new story version)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reelforge.audio.state import AudioError
from reelforge.story import service as story_service
from reelforge.story.errors import StoryInvalid
from reelforge.story.schema import Cue, Story
from reelforge.story.yamlio import parse_story, story_to_yaml, validate_story_data

if TYPE_CHECKING:
    from reelforge.context import AppContext

NO_STORY = "There is no story yet."


def load_story(ctx: AppContext, project_id: str) -> Story:
    current = story_service.current_version(ctx, project_id)
    if current is None:
        raise AudioError(409, NO_STORY)
    try:
        return parse_story(current.yaml_text)
    except StoryInvalid:
        raise AudioError(409, NO_STORY) from None


def load_cues(ctx: AppContext, project_id: str) -> list[Cue]:
    return list(load_story(ctx, project_id).audio or [])


def invalid(exc: StoryInvalid) -> AudioError:
    return AudioError(
        422,
        "story.yaml is invalid",
        [{"path": e.path, "message": e.message} for e in exc.errors],
    )


def write_cues(ctx: AppContext, project_id: str, cues: list[Cue]) -> list[Cue]:
    """Save `cues` as the story's audio list; raises AudioError(422) listing every problem."""
    story = load_story(ctx, project_id)
    data = story.model_dump(mode="json", exclude_none=True)
    data["audio"] = [c.model_dump(mode="json", exclude_none=True) for c in cues]
    try:
        updated = validate_story_data(data)
    except StoryInvalid as exc:
        raise invalid(exc) from None
    if updated == story:
        return list(updated.audio or [])
    story_service.save_version(ctx, project_id, story_to_yaml(updated), keep_stage=True)
    return list(updated.audio or [])
