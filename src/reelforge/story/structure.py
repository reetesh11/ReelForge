"""`story.structure` job: storyline text to a validated story via the LLM."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from reelforge.adapters.base import AdapterError, CancelToken
from reelforge.adapters.llm import ChatMessage
from reelforge.api.schemas import StoryVersionOut, StructureRequest
from reelforge.db.models import Job
from reelforge.story import service
from reelforge.story.age import check_age
from reelforge.story.errors import StoryInvalid
from reelforge.story.prompts import REPAIR_PROMPT, STRUCTURE_PROMPT, load_prompt
from reelforge.story.schema import Story, story_json_schema
from reelforge.story.yamlio import story_to_yaml, validate_story_data

if TYPE_CHECKING:
    from reelforge.context import AppContext

MIN_SCENES = 4
MAX_SCENES = 8
DURATION_SLACK_S = 0.05
FAILURE_PREFIX = "The model's story didn't match the schema after one repair attempt: "
_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def response_schema() -> dict[str, Any]:
    story = story_json_schema()
    defs: dict[str, Any] = story.pop("$defs", {})
    return {
        "type": "object",
        "properties": {
            "story": {"anyOf": [story, {"type": "null"}]},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "question": {"type": "string"}},
                    "required": ["path", "question"],
                },
            },
        },
        "required": ["story", "questions"],
        "$defs": defs,
    }


def build_messages(req: StructureRequest) -> list[ChatMessage]:
    parts = [f"Storyline:\n{req.storyline.strip()}"]
    for label, value in (
        ("Characters", req.characters),
        ("Backgrounds/locations", req.locations),
        ("Product placement", req.product),
        ("Dialogue", req.dialogue),
        ("Style", req.style),
    ):
        if value and value.strip():
            parts.append(f"{label}:\n{value.strip()}")
    if req.language:
        parts.append(f"Language: {req.language}")
    parts.append(f"Target length: {req.target_seconds} seconds")
    if req.library_picks:
        parts.append("Saved characters to reuse (library ids): " + ", ".join(req.library_picks))
    if req.answers:
        lines = [f"- {a.path} ({a.question}): {a.answer}" for a in req.answers]
        parts.append("Answers to earlier questions:\n" + "\n".join(lines))
    return [
        {"role": "system", "content": load_prompt(STRUCTURE_PROMPT)},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def remove_path(data: Any, path: str) -> None:
    """Delete the value at `path` (`scenes[1].setting`, `characters.tomato.look`) if present."""
    tokens = [(m.group(1), m.group(2)) for m in _PATH_TOKEN.finditer(path)]
    if not tokens:
        return
    node = data
    for key, index in tokens[:-1]:
        if key is not None and isinstance(node, dict):
            node = node.get(key)  # type: ignore[reportUnknownMemberType]
        elif index is not None and isinstance(node, list):
            i = int(index)
            node = node[i] if i < len(node) else None  # type: ignore[reportUnknownVariableType]
        else:
            return
        if node is None:
            return
    key, index = tokens[-1]
    if key is not None and isinstance(node, dict):
        node.pop(key, None)  # type: ignore[reportUnknownMemberType]


@dataclass
class Outcome:
    errors: list[str] = field(default_factory=lambda: [])
    story: Story | None = None
    questions: list[dict[str, str]] = field(default_factory=lambda: [])
    draft_yaml: str | None = None


def _questions(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:  # type: ignore[reportUnknownVariableType]
            if (
                isinstance(item, dict)
                and isinstance(item.get("path"), str)  # type: ignore[reportUnknownMemberType]
                and isinstance(item.get("question"), str)  # type: ignore[reportUnknownMemberType]
            ):
                out.append({"path": item["path"], "question": item["question"]})  # type: ignore[reportUnknownVariableType]
    return out


def _drop_bad_ages(data: dict[str, Any]) -> None:
    """A proposed age that is not a whole number from 1 to 120 is dropped, not an error."""
    characters: Any = data.get("characters")
    if not isinstance(characters, dict):
        return
    for character in characters.values():  # type: ignore[reportUnknownVariableType]
        if isinstance(character, dict) and "age" in character:
            try:
                check_age(character["age"])  # type: ignore[reportUnknownArgumentType]
            except ValueError:
                character.pop("age", None)  # type: ignore[reportUnknownMemberType]


def _apply_server_fields(data: dict[str, Any], req: StructureRequest) -> None:
    data["version"] = 1
    data["target_seconds"] = req.target_seconds
    if req.language:
        data["language"] = req.language
    if req.style and req.style.strip():
        data["style"] = req.style.strip()
    user_dialogue = bool(req.dialogue and req.dialogue.strip())
    _drop_bad_ages(data)
    scenes: Any = data.get("scenes")
    if isinstance(scenes, list):
        for scene in scenes:  # type: ignore[reportUnknownVariableType]
            if not isinstance(scene, dict):
                continue
            scene.pop("suggested", None)  # type: ignore[reportUnknownMemberType]
            if not user_dialogue and scene.get("line"):  # type: ignore[reportUnknownMemberType]
                scene["suggested"] = True


def structural_errors(story: Story) -> list[str]:
    errors: list[str] = []
    count = len(story.scenes)
    if not MIN_SCENES <= count <= MAX_SCENES:
        errors.append(f"scenes: must have {MIN_SCENES} to {MAX_SCENES} scenes, got {count}")
    total = sum(s.duration or 0.0 for s in story.scenes)
    if total > story.target_seconds + DURATION_SLACK_S:
        errors.append(
            f"scenes: total duration {total:g} s is over the {story.target_seconds} s target"
        )
    for key, character in story.characters.items():
        if "\n" in character.look or "\r" in character.look:
            errors.append(f"characters.{key}.look: must be a single line")
    return errors


def evaluate(raw: str, req: StructureRequest) -> Outcome:
    try:
        parsed: Any = json.loads(raw)
    except ValueError:
        return Outcome(errors=["response: not valid JSON"])
    if not isinstance(parsed, dict):
        return Outcome(errors=["response: must be a JSON object"])
    questions = _questions(parsed.get("questions"))  # type: ignore[reportUnknownMemberType]
    story_data: Any = parsed.get("story")  # type: ignore[reportUnknownMemberType]
    if story_data is None:
        if questions:
            return Outcome(questions=questions)
        return Outcome(errors=["story: required when there are no questions"])
    if not isinstance(story_data, dict):
        return Outcome(errors=["story: must be an object"])
    data: dict[str, Any] = copy.deepcopy(story_data)  # type: ignore[reportUnknownArgumentType]
    _apply_server_fields(data, req)
    if questions:
        for q in questions:
            remove_path(data, q["path"])
        try:
            draft = validate_story_data(data)
        except StoryInvalid:
            return Outcome(questions=questions)
        return Outcome(questions=questions, draft_yaml=story_to_yaml(draft))
    try:
        story = validate_story_data(data)
    except StoryInvalid as exc:
        return Outcome(errors=[str(e) for e in exc.errors])
    problems = structural_errors(story)
    if problems:
        return Outcome(errors=problems)
    return Outcome(story=story)


async def structure_story(
    ctx: AppContext, job: Job, progress: Callable[[int, str], None], cancel: CancelToken
) -> None:
    req = StructureRequest.model_validate(job.payload)
    project_id = job.project_id
    if project_id is None:
        raise AdapterError("story.structure needs a project")
    messages = build_messages(req)
    schema = response_schema()
    heavy_next = any(j.heavy for j in ctx.queue.list(status="queued"))

    progress(10, "Asking the model")
    raw = await ctx.llm.chat(messages, schema=schema, heavy_next=heavy_next)
    if cancel.cancelled:
        raise AdapterError("cancelled")
    outcome = evaluate(raw, req)
    if outcome.errors:
        progress(60, "Repairing the story")
        repair = load_prompt(REPAIR_PROMPT).replace("{{errors}}", "\n".join(outcome.errors))
        second = [
            *messages,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": repair},
        ]
        raw = await ctx.llm.chat(second, schema=schema, heavy_next=heavy_next)
        if cancel.cancelled:
            raise AdapterError("cancelled")
        outcome = evaluate(raw, req)
        if outcome.errors:
            raise AdapterError(FAILURE_PREFIX + "; ".join(outcome.errors))

    progress(90, "Saving")
    result: dict[str, Any]
    if outcome.story is not None:
        saved = service.save_version(ctx, project_id, story_to_yaml(outcome.story))
        version = StoryVersionOut(
            id=saved.id,
            version=saved.version,
            is_current=saved.is_current,
            approved_at=saved.approved_at,
            created_at=saved.created_at,
            affected=[
                {"owner_type": a.owner_type, "owner_id": a.owner_id, "kinds": a.kinds}  # type: ignore[misc]
                for a in saved.affected
            ],
        )
        result = {"version": version.model_dump(mode="json"), "questions": [], "draft_yaml": None}
    else:
        result = {"version": None, "questions": outcome.questions, "draft_yaml": outcome.draft_yaml}
    ctx.queue.update_running(job.id, result=result)
