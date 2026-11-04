"""The emotion mapping table (`emotions.toml`): emotion to model and post-processing levers.

The file is read again for every use, so an edit applies to the next take.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from reelforge.story.markup import EMOTIONS

PACKAGED_MAPPING = Path(__file__).resolve().parent / "emotions.toml"
DEFAULT_GAP_MS = 150


class MappingError(ValueError):
    """The mapping file is missing or does not describe every emotion."""


@dataclass(frozen=True)
class PostSettings:
    semitones: float = 0.0
    gain_db: float = 0.0
    pause_s: float = 0.0
    tempo: float = 1.0


@dataclass(frozen=True)
class EmotionRule:
    tags: list[str]
    tag_position: Literal["prefix", "suffix"]
    pitch: str
    duration_scale: float
    generation: dict[str, float] = field(default_factory=lambda: {})
    post: PostSettings = PostSettings()


@dataclass(frozen=True)
class KokoroAge:
    prefer: list[str]
    semitones: float = 0.0


@dataclass(frozen=True)
class Mapping:
    phrase_gap_ms: int
    emotions: dict[str, EmotionRule]
    kokoro: dict[str, KokoroAge] = field(default_factory=lambda: {})

    def rule(self, emotion: str) -> EmotionRule | None:
        return self.emotions.get(emotion)

    def kokoro_age(self, band: str) -> KokoroAge | None:
        return self.kokoro.get(band)


def _table(data: Any, where: str, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MappingError(f"{path.name}: {where} must be a table.")
    return data  # type: ignore[reportUnknownVariableType]


def _number(value: Any, where: str, path: Path) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MappingError(f"{path.name}: {where} must be a number.")
    return float(value)


def _rule(name: str, data: dict[str, Any], path: Path) -> EmotionRule:
    where = f"[emotion.{name}]"
    tags: Any = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):  # type: ignore[reportUnknownVariableType]
        raise MappingError(f"{path.name}: {where} tags must be a list of text.")
    position = data.get("tag_position", "prefix")
    if position not in ("prefix", "suffix"):
        raise MappingError(f'{path.name}: {where} tag_position must be "prefix" or "suffix".')
    pitch = data.get("pitch", "")
    if not isinstance(pitch, str):
        raise MappingError(f"{path.name}: {where} pitch must be text.")
    gen = _table(data.get("generation", {}), f"{where} generation", path)
    post = _table(data.get("post", {}), f"{where} post", path)
    return EmotionRule(
        tags=[str(t) for t in tags],  # type: ignore[reportUnknownVariableType]
        tag_position=position,
        pitch=pitch,
        duration_scale=_number(data.get("duration_scale", 1.0), f"{where} duration_scale", path),
        generation={str(k): _number(v, f"{where} generation {k}", path) for k, v in gen.items()},
        post=PostSettings(
            semitones=_number(post.get("semitones", 0.0), f"{where} post semitones", path),
            gain_db=_number(post.get("gain_db", 0.0), f"{where} post gain_db", path),
            pause_s=_number(post.get("pause_s", 0.0), f"{where} post pause_s", path),
            tempo=_number(post.get("tempo", 1.0), f"{where} post tempo", path),
        ),
    )


def load_mapping(path: Path) -> Mapping:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MappingError(f"Can't read the emotion mapping file {path}: {exc.strerror}.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MappingError(
            f"The emotion mapping file {path.name} is not valid TOML: {exc}"
        ) from exc
    phrase = _table(raw.get("phrase", {}), "[phrase]", path)
    gap = _number(phrase.get("gap_ms", DEFAULT_GAP_MS), "[phrase] gap_ms", path)
    emotions_raw = _table(raw.get("emotion", {}), "[emotion]", path)
    emotions: dict[str, EmotionRule] = {}
    for name in EMOTIONS:
        if name not in emotions_raw:
            raise MappingError(f"{path.name} has no [emotion.{name}] table.")
        emotions[name] = _rule(name, _table(emotions_raw[name], f"[emotion.{name}]", path), path)
    kokoro: dict[str, KokoroAge] = {}
    for band, body in _table(raw.get("kokoro_age", {}), "[kokoro_age]", path).items():
        table = _table(body, f"[kokoro_age.{band}]", path)
        prefer: Any = table.get("prefer", [])
        kokoro[band] = KokoroAge(
            prefer=[str(p) for p in prefer] if isinstance(prefer, list) else [],  # type: ignore[reportUnknownVariableType]
            semitones=_number(table.get("semitones", 0.0), f"[kokoro_age.{band}] semitones", path),
        )
    return Mapping(phrase_gap_ms=round(gap), emotions=emotions, kokoro=kokoro)
