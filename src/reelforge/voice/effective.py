"""What a line will sound like ("effective"), what a take recorded, and when they differ.

Pure functions over a `LinePlan` and a take's params, so the voice board, the "How this will
sound" panel and the stale check all read the same values.
"""

from __future__ import annotations

from typing import Any

from reelforge.voice.mapping import Mapping
from reelforge.voice.plan import LinePlan

# What decides how a phrase sounds; compared between a take and the current plan.
_PHRASE_KEYS = (
    "emotion",
    "tags",
    "tag_position",
    "pitch",
    "duration_scale",
    "generation",
    "post",
    "reference",
)


def reference_label(reference: str, emotion: str | None) -> str:
    if reference == "emotion" and emotion:
        return f"{emotion.capitalize()} reference clip"
    return "Neutral reference"


def _phrase_view(rec: dict[str, Any], speed: float) -> dict[str, Any]:
    scale = float(rec["duration_scale"])
    out: dict[str, Any] = {
        "text": rec["text"],
        "emotion": rec["emotion"],
        "tags": list(rec["tags"]),
        "tag_position": rec["tag_position"],
        "pitch": rec["pitch"],
        "duration_scale": scale,
        "duration_factor": round(scale / speed, 4) if speed else scale,
        "generation": dict(rec["generation"]),
        "post": dict(rec["post"]),
        "reference": rec["reference"],
        "reference_label": reference_label(rec["reference"], rec["emotion"]),
    }
    return out


def effective_body(plan: LinePlan) -> dict[str, Any] | None:
    """The `effective` object of a line, or None when delivery is the plain default."""
    if plan.is_default:
        return None
    out: dict[str, Any] = {"emotion_applied": plan.emotion_applied, "speed": plan.speed}
    if plan.age_band is not None:
        out["age_band"] = plan.age_band
    if plan.gap_ms is not None:
        out["gap_ms"] = plan.gap_ms
    out["phrases"] = [_phrase_view(ph.recorded(), plan.speed) for ph in plan.phrases]
    return out


def take_settings(params: dict[str, Any]) -> dict[str, Any] | None:
    """A take's recorded applied values, or None when it recorded none."""
    keys = ("phrases", "age_band", "gap_ms", "duration_requested_s")
    if not any(k in params for k in keys):
        return None
    speed = float(params.get("speed") or 1.0)
    out: dict[str, Any] = {"emotion_applied": True, "speed": speed}
    for key in ("age_band", "gap_ms"):
        if key in params:
            out[key] = params[key]
    views: list[dict[str, Any]] = []
    recorded: list[dict[str, Any]] = params.get("phrases") or []
    for rec in recorded:
        view = _phrase_view(rec, speed)
        if rec.get("duration_requested_s") is not None:
            view["duration_requested_s"] = rec["duration_requested_s"]
        views.append(view)
    out["phrases"] = views
    if "duration_requested_s" in params:
        out["duration_requested_s"] = params["duration_requested_s"]
    return out


def _canon(body: dict[str, Any] | None, *, phrases: bool = True) -> dict[str, Any]:
    body = body or {}
    items: list[dict[str, Any]] = body.get("phrases") or []
    return {
        "speed": body.get("speed", 1.0),
        "age_band": body.get("age_band"),
        "gap_ms": body.get("gap_ms"),
        "phrases": [{k: ph.get(k) for k in _PHRASE_KEYS} for ph in items] if phrases else [],
    }


def settings_changed(
    plan: LinePlan, effective: dict[str, Any] | None, recorded: dict[str, Any] | None
) -> bool:
    """The active take's recorded values differ from what the line would use now."""
    current = _canon(effective, phrases=plan.records_phrases)
    return _canon(recorded) != current


def values_stale(
    params: dict[str, Any],
    plan: LinePlan,
    mapping: Mapping | None,
    gap_ms: int,
    clips: dict[str, str],
) -> bool:
    """A take is stale when what it recorded no longer matches the mapping, the phrase gap, the
    emotion clips it used or the character's age band.

    `clips` maps an emotion to the artifact id of its current clip. Takes without emotions are
    never stale from a mapping change.
    """
    if params.get("source") != "tts":
        return False
    if params.get("age_band") != plan.age_band:
        return True
    recorded: list[dict[str, Any]] = params.get("phrases") or []
    for ph in recorded:
        emotion = ph.get("emotion")
        if ph.get("reference") == "emotion" and clips.get(str(emotion)) != ph.get(
            "reference_artifact_id"
        ):
            return True
        rule = mapping.rule(emotion) if mapping is not None and emotion else None
        if rule is None:
            continue
        now = {
            "tags": list(rule.tags),
            "tag_position": rule.tag_position,
            "pitch": rule.pitch,
            "duration_scale": rule.duration_scale,
            "generation": dict(rule.generation),
            "post": {
                "semitones": rule.post.semitones,
                "gain_db": rule.post.gain_db,
                "pause_s": rule.post.pause_s,
            },
        }
        if any(ph.get(k) != v for k, v in now.items()):
            return True
    return "gap_ms" in params and params["gap_ms"] != gap_ms
