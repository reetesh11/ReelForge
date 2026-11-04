"""Emotion markup in a story line: `<sad>...</sad>`, and the text shown or spoken."""

from __future__ import annotations

import re
from dataclasses import dataclass

EMOTIONS: tuple[str, ...] = ("happy", "sad", "fear", "anger")
BAD_MARKUP = "Emotion markup is not valid: close every <emotion> tag and do not nest them."

_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9_-]*)>")
_NONVERBAL = re.compile(r"\[[^\]]*\]")
_SPACES = re.compile(r"\s+")


def unknown_emotion(value: str) -> str:
    return f'Unknown emotion "{value}". Use one of: {", ".join(EMOTIONS)}.'


def check_emotion(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in EMOTIONS:
        raise ValueError(unknown_emotion(str(value)))
    return value


@dataclass(frozen=True)
class Segment:
    text: str
    emotion: str | None


def parse_segments(raw: str) -> list[Segment]:
    """Split a line into unmarked and marked segments, in order."""
    segments: list[Segment] = []
    open_emotion: str | None = None
    pos = 0

    def add(text: str, emotion: str | None) -> None:
        if text.strip():
            segments.append(Segment(text.strip(), emotion))

    for m in _TAG.finditer(raw):
        closing, name = m.group(1) == "/", m.group(2)
        if name not in EMOTIONS:
            raise ValueError(unknown_emotion(name))
        piece = raw[pos : m.start()]
        pos = m.end()
        if closing:
            if open_emotion != name or not piece.strip():
                raise ValueError(BAD_MARKUP)
            add(piece, open_emotion)
            open_emotion = None
        else:
            if open_emotion is not None:
                raise ValueError(BAD_MARKUP)
            add(piece, None)
            open_emotion = name
    if open_emotion is not None:
        raise ValueError(BAD_MARKUP)
    add(raw[pos:], None)
    return segments


def _clean(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def speech_text(raw: str) -> str:
    """The line without emotion markup; typed `[...]` tags stay."""
    return _clean(_TAG.sub(" ", raw))


def display_text(raw: str) -> str:
    """The line as shown on screen and in captions: no markup and no `[...]` tags."""
    return _clean(_NONVERBAL.sub(" ", _TAG.sub(" ", raw)))
