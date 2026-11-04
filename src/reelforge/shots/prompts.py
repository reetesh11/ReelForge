"""Shot prompts: the look text is inserted by code, the LLM only writes the motion sentence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reelforge.adapters.llm import ChatMessage

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
MOTION_PROMPT = "motion.v1.md"
TALKING_SUFFIX = "The character speaks naturally to the camera; the lips follow the audio."


def motion_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"motion_prompt": {"type": "string"}},
        "required": ["motion_prompt"],
    }


def motion_messages(*, action: str, setting: str, shot_type: str) -> list[ChatMessage]:
    parts = [f"Action: {action.strip()}"]
    if setting.strip():
        parts.append(f"Setting: {setting.strip()}")
    parts.append(f"Shot type: {shot_type}")
    return [
        {"role": "system", "content": (PROMPT_DIR / MOTION_PROMPT).read_text(encoding="utf-8")},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def compose_motion_prompt(*, motion: str, look: str, shot_type: str) -> str:
    """The motion sentence, then the character's look verbatim (appearance only)."""
    parts = [_sentence(motion)]
    if look.strip():
        parts.append(_sentence(f"The character looks exactly like this: {look}"))
    if shot_type == "talking":
        parts.append(TALKING_SUFFIX)
    return " ".join(p for p in parts if p)
