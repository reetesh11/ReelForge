"""Suggest sound cues from the sound directions written in the storyline and dialogue."""

from __future__ import annotations

import re

from reelforge.story.schema import Cue, CueTime, Story

MAX_PROMPT = 160
SFX_SECONDS = 1.5
SILENCE_SECONDS = 1.0
_SENTENCES = re.compile(r"[.!?\n]+")
_WORDS = re.compile(r"[a-z]{3,}")
_STOP = frozenset(
    (
        "the and with for from that this then his her its they them into onto over under out are "
        "was were has have had she him you your our but not all one two for an in on at to of as "
        "is it"
    ).split()
)

# (kind, pattern, canonical prompt or None to use the sentence)
_RULES: list[tuple[str, re.Pattern[str], str | None]] = [
    ("silence", re.compile(r"\bsilen(ce|t)\b", re.I), None),
    (
        "music",
        re.compile(
            r"\btrack\s*\d+|\b(background\s+)?music\b|\bscore\b|\bsoundtrack\b|\bshehnai\b|\bdholak\b",
            re.I,
        ),
        None,
    ),
    (
        "ambience",
        re.compile(
            r"\bambien(ce|t)\b|\bambiance\b|\bcrowd\s+(murmur|noise|chatter)\b"
            r"|\bbackground\s+(noise|chatter)\b",
            re.I,
        ),
        None,
    ),
    ("sfx", re.compile(r"\bgong\b", re.I), "gong slam"),
    ("sfx", re.compile(r"\bdrum\s*roll\b", re.I), "drum roll"),
    ("sfx", re.compile(r"\b(ceramic|plate)\b[^.]*\bcrash|\bcrash\b", re.I), "ceramic crash"),
    ("sfx", re.compile(r"\bcrinkl\w*", re.I), "packaging crinkle"),
    ("sfx", re.compile(r"\bcrunch\w*", re.I), "loud crunch"),
    ("sfx", re.compile(r"\b(whoosh|thud|bang|splash|ding)\b", re.I), None),
]


def _tokens(text: str) -> set[str]:
    return {w for w in _WORDS.findall(text.lower()) if w not in _STOP}


def _scene_for(sentence: str, story: Story) -> str:
    """The scene whose action shares most words with the sentence; the first one when none do."""
    words = _tokens(sentence)
    best, best_score = story.scenes[0].id, 0
    for scene in story.scenes:
        score = len(words & _tokens(scene.action))
        if score > best_score:
            best, best_score = scene.id, score
    return best


def _clean(sentence: str) -> str:
    return " ".join(sentence.split())[:MAX_PROMPT]


def _prompt(kind: str, canonical: str | None, sentence: str, match: re.Match[str]) -> str:
    if canonical is not None:
        return canonical
    if kind == "sfx":
        return match.group(0).lower()
    return _clean(sentence)


def suggest_cues(text: str, story: Story) -> list[Cue]:
    """Keyword-based cues, all suggested; text without sound directions gives none."""
    last = story.scenes[-1].id
    out: list[Cue] = []
    seen: set[tuple[str, str, str]] = set()
    counts: dict[str, int] = {}
    for sentence in _SENTENCES.split(text):
        if not sentence.strip():
            continue
        for kind, pattern, canonical in _RULES:
            match = pattern.search(sentence)
            if match is None:
                continue
            scene = _scene_for(sentence, story)
            prompt = _prompt(kind, canonical, sentence, match)
            if (kind, scene, prompt) in seen:
                continue
            seen.add((kind, scene, prompt))
            base = f"{kind}_{scene}"
            counts[base] = counts.get(base, 0) + 1
            cue_id = base if counts[base] == 1 else f"{base}_{counts[base]}"
            fields: dict[str, object] = {
                "id": cue_id,
                "kind": kind,
                "start": CueTime(scene=scene),
                "state": "suggested",
            }
            if kind in ("music", "ambience"):
                fields["end"] = CueTime(scene=last, at="scene_end")
            else:
                fields["duration"] = SILENCE_SECONDS if kind == "silence" else SFX_SECONDS
            if kind != "silence":
                fields["prompt"] = prompt
            out.append(Cue.model_validate(fields))
    return out


def merge_suggestions(existing: list[Cue], new: list[Cue]) -> list[Cue]:
    """`existing` unchanged, then the suggestions whose id and (kind, scene, prompt) are new."""
    ids = {c.id for c in existing}
    keys = {(c.kind, c.start.scene, c.prompt) for c in existing}
    merged = list(existing)
    for cue in new:
        key = (cue.kind, cue.start.scene, cue.prompt)
        if cue.id in ids or key in keys:
            continue
        ids.add(cue.id)
        keys.add(key)
        merged.append(cue)
    return merged
