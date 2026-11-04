"""Turn a story line, its emotion, speed, age and voice into a list of phrase plans.

One code path serves generation, the "How this will sound" panel and the stale check.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from reelforge.story.age import age_band
from reelforge.story.markup import Segment, display_text, parse_segments, speech_text
from reelforge.voice.mapping import EmotionRule, Mapping, PostSettings

Reference = Literal["neutral", "emotion"]


@dataclass(frozen=True)
class PhrasePlan:
    text: str  # phrase text: markup removed, typed [...] tags kept, no mapping tag
    model_text: str  # what the model is given: `text` with the mapping tag inserted
    emotion: str | None
    tags: list[str]
    tag_position: str
    pitch: str
    instruct: str | None  # comma-joined pitch and age band (OmniVoice only)
    duration_scale: float
    duration_factor: float  # duration_scale / speed; 1.0 means no duration target
    generation: dict[str, float]
    post: PostSettings
    reference: Reference

    def recorded(self) -> dict[str, Any]:
        """The values stored in a take's params (and compared later for staleness)."""
        return {
            "text": self.text,
            "emotion": self.emotion,
            "tags": list(self.tags),
            "tag_position": self.tag_position,
            "pitch": self.pitch,
            "instruct": self.instruct,
            "duration_scale": self.duration_scale,
            "generation": dict(self.generation),
            "post": {
                "semitones": self.post.semitones,
                "gain_db": self.post.gain_db,
                "pause_s": self.post.pause_s,
            },
            "reference": self.reference,
        }


@dataclass(frozen=True)
class LinePlan:
    phrases: list[PhrasePlan]
    speed: float
    emotion_applied: bool
    age_band: str | None
    gap_ms: int | None  # only for lines with more than one phrase
    requested: bool = False  # an emotion was asked for (it may not be applied, as on Kokoro)

    @property
    def has_emotion(self) -> bool:
        return any(p.emotion is not None for p in self.phrases)

    @property
    def is_default(self) -> bool:
        """No emotion, speed 1.0 and no age: delivery is the plain default."""
        return (
            not self.requested
            and not self.has_emotion
            and self.speed == 1.0
            and self.age_band is None
        )

    @property
    def records_phrases(self) -> bool:
        return len(self.phrases) > 1 or (self.emotion_applied and self.has_emotion)


def _with_tags(text: str, rule: EmotionRule | None) -> str:
    if rule is None or not rule.tags:
        return text
    tags = " ".join(rule.tags)
    return f"{tags} {text}" if rule.tag_position == "prefix" else f"{text} {tags}"


def _instruct(pitch: str, band: str | None) -> str | None:
    parts = [p for p in (pitch, band) if p]
    return ", ".join(parts) if parts else None


def _segments(raw: str, picker_emotion: str | None) -> list[Segment]:
    if picker_emotion is not None:
        return [Segment(speech_text(raw), picker_emotion)]  # the picker overrides the markup
    return parse_segments(raw) or [Segment(raw.strip(), None)]


def plan_line(
    raw: str,
    picker_emotion: str | None,
    *,
    mapping: Mapping,
    voice_model: str,
    speed: float,
    age: int | None,
    has_clip: Callable[[str], bool] | None = None,
    gap_ms: int | None = None,
) -> LinePlan:
    band = age_band(age) if age is not None else None
    if voice_model == "kokoro":
        return _kokoro_plan(raw, picker_emotion, mapping, speed, band)
    phrases: list[PhrasePlan] = []
    for seg in _segments(raw, picker_emotion):
        rule = mapping.rule(seg.emotion) if seg.emotion else None
        scale = rule.duration_scale if rule is not None else 1.0
        clip = bool(seg.emotion and has_clip is not None and has_clip(seg.emotion))
        phrases.append(
            PhrasePlan(
                text=seg.text,
                model_text=_with_tags(seg.text, rule),
                emotion=seg.emotion if rule is not None else None,
                tags=list(rule.tags) if rule is not None else [],
                tag_position=rule.tag_position if rule is not None else "prefix",
                pitch=rule.pitch if rule is not None else "",
                instruct=_instruct(rule.pitch if rule is not None else "", band),
                duration_scale=scale,
                duration_factor=round(scale / speed, 4),
                generation=dict(rule.generation) if rule is not None else {},
                post=rule.post if rule is not None else PostSettings(),
                reference="emotion" if clip else "neutral",
            )
        )
    multi = len(phrases) > 1
    gap = (gap_ms if gap_ms is not None else mapping.phrase_gap_ms) if multi else None
    return LinePlan(phrases, speed, True, band, gap, any(p.emotion for p in phrases))


def _kokoro_plan(
    raw: str, picker_emotion: str | None, mapping: Mapping, speed: float, band: str | None
) -> LinePlan:
    """Kokoro takes no emotion levers: one phrase of plain text; age is a small pitch shift."""
    shift = mapping.kokoro_age(band) if band is not None else None
    phrase = PhrasePlan(
        text=display_text(raw),
        model_text=display_text(raw),
        emotion=None,
        tags=[],
        tag_position="prefix",
        pitch="",
        instruct=None,
        duration_scale=1.0,
        duration_factor=1.0,
        generation={},
        post=PostSettings(semitones=shift.semitones) if shift is not None else PostSettings(),
        reference="neutral",
    )
    asked = picker_emotion is not None or any(seg.emotion for seg in parse_segments(raw))
    return LinePlan([phrase], speed, False, band, None, asked)
