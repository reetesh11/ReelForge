"""Versioned prompt for the character bible line, plus the image prompt builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reelforge.adapters.llm import ChatMessage

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
BIBLE_PROMPT = "bible.v1.md"
NAME_LABEL = "Character name: "
LOOK_LABEL = "Look: "
STYLE_LABEL = "Style: "
FRAMING = "front-facing, plain background, 9:16 full body"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def bible_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"bible_line": {"type": "string"}},
        "required": ["bible_line"],
    }


def bible_messages(name: str, look: str, style: str) -> list[ChatMessage]:
    parts = [f"{NAME_LABEL}{name}", f"{LOOK_LABEL}{look}"]
    if style.strip():
        parts.append(f"{STYLE_LABEL}{style.strip()}")
    return [
        {"role": "system", "content": load_prompt(BIBLE_PROMPT)},
        {"role": "user", "content": "\n".join(parts)},
    ]


def image_prompt(bible_line: str, style: str) -> str:
    parts = [bible_line.strip().rstrip(".")]
    if style.strip():
        parts.append(style.strip())
    parts.append(FRAMING)
    return ". ".join(parts)
