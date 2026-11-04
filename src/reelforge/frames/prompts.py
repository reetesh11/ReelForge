"""Frame prompts: the look text is inserted by code, the LLM only writes the scene sentence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reelforge.adapters.llm import ChatMessage

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SCENE_PROMPT = "scene.v1.md"

FRAMING_PHRASES: dict[str, str] = {
    "wide": "wide shot, the whole scene and the characters' full bodies in view",
    "medium": "medium shot, characters framed from the waist up",
    "closeup": "close-up shot, the face and shoulders fill the frame",
}
PRODUCT_PHRASE = (
    "the real product pack from the reference image is held in hand or placed on the table, "
    "pack design unchanged"
)


def scene_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"scene_sentence": {"type": "string"}},
        "required": ["scene_sentence"],
    }


def scene_messages(*, action: str, setting: str, line: str) -> list[ChatMessage]:
    parts = [f"Action: {action.strip()}"]
    if setting.strip():
        parts.append(f"Setting: {setting.strip()}")
    if line.strip():
        parts.append(f"Spoken line: {line.strip()}")
    return [
        {"role": "system", "content": (PROMPT_DIR / SCENE_PROMPT).read_text(encoding="utf-8")},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def compose_frame_prompt(
    *,
    scene_sentence: str,
    look: str,
    framing: str,
    style: str,
    other_looks: list[tuple[str, str]],
    product: bool,
) -> str:
    """Scene sentence, the master's look verbatim, other characters' looks verbatim, framing,
    style and (only when asked) the product phrase."""
    parts = [_sentence(scene_sentence), _sentence(look)]
    for name, other in other_looks:
        parts.append(_sentence(f"Also in the scene, {name}: {other}"))
    parts.append(_sentence(FRAMING_PHRASES[framing]))
    if product:
        parts.append(_sentence(PRODUCT_PHRASE))
    if style.strip():
        parts.append(_sentence(style))
    return " ".join(p for p in parts if p)
