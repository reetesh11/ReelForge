"""The story.yaml schema (Pydantic v2, strict, no coercion)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from reelforge.story.age import check_age
from reelforge.story.markup import check_emotion, parse_segments

_STRICT = ConfigDict(extra="forbid", strict=True)

CharacterKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
SceneId = Annotated[str, StringConstraints(pattern=r"^s\d+$")]
Language = Literal["hindi", "english", "hinglish"]


class Voice(BaseModel):
    model_config = _STRICT

    mode: Literal["preset", "designed", "cloned"]
    ref: str | None = None
    reference_clip: str | None = None
    speed: float | None = Field(default=None, gt=0)


class Character(BaseModel):
    model_config = _STRICT

    library_id: str | None = None
    name: str
    look: str = Field(min_length=1)
    voice: Voice | None = None
    age: int | None = None

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: object) -> int | None:
        return check_age(value)


class Product(BaseModel):
    model_config = _STRICT

    name: str
    asset: str | None = None


class Scene(BaseModel):
    model_config = _STRICT

    id: SceneId
    setting: str | None = None
    action: str
    framing: Literal["wide", "medium", "closeup"] | None = None
    duration: float | None = Field(default=None, gt=0)
    speaker: str | None = None
    line: str | None = None
    product_in_shot: bool | None = None
    continue_from: str | None = None
    end_card: bool | None = None
    suggested: bool | None = None
    emotion: str | None = None

    @field_validator("emotion", mode="before")
    @classmethod
    def _emotion(cls, value: object) -> str | None:
        return check_emotion(value if value is None else str(value))

    @field_validator("line")
    @classmethod
    def _line(cls, value: str | None) -> str | None:
        if value:
            parse_segments(value)
        return value


class Music(BaseModel):
    model_config = _STRICT

    mode: str
    track: str | None = None
    duck_under_speech: bool | None = None


class Captions(BaseModel):
    model_config = _STRICT

    style: str
    script: str


class CrossFieldIssues(ValueError):
    """Carried through Pydantic's `value_error` so every issue keeps its own path."""

    def __init__(self, issues: list[tuple[str, str]]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{p}: {m}" for p, m in issues))


class Story(BaseModel):
    model_config = _STRICT

    version: Literal[1]
    title: str = Field(min_length=1)
    language: Language
    style: str = ""
    aspect: str = Field(default="9:16", pattern=r"^\d+:\d+$")
    fps: int = Field(default=24, gt=0)
    target_seconds: int = Field(default=12, gt=0, le=60)
    brand_kit: str | None = None
    characters: dict[CharacterKey, Character]
    product: Product | None = None
    scenes: list[Scene] = Field(min_length=1)
    music: Music | None = None
    captions: Captions | None = None

    @model_validator(mode="after")
    def _cross_field(self) -> Self:
        issues: list[tuple[str, str]] = []
        seen: set[str] = set()
        ids = {s.id for s in self.scenes}
        for i, scene in enumerate(self.scenes):
            if scene.id in seen:
                issues.append((f"scenes[{i}].id", f"duplicate scene id {scene.id}"))
            seen.add(scene.id)
            if scene.speaker is not None and scene.speaker not in self.characters:
                issues.append(
                    (f"scenes[{i}].speaker", f"{scene.speaker} is not a character in this story")
                )
            if scene.continue_from is not None and scene.continue_from not in ids:
                issues.append(
                    (f"scenes[{i}].continue_from", f"{scene.continue_from} is not a scene id")
                )
        if issues:
            raise CrossFieldIssues(issues)
        return self


def story_json_schema() -> dict[str, Any]:
    return Story.model_json_schema()
