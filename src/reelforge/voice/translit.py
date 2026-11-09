"""Hinglish (Hindi in Latin letters) to Devanagari, so the Hindi voice models can read it.

The Hindi voices are trained on Devanagari. Given romanised text ("Maza nahi aaya!") OmniVoice
can produce a beep or noise and Kokoro mispronounces it, so every Hindi line is converted before
it reaches the model. Inline tags such as `[sigh]` pass through untouched.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from reelforge.adapters.llm import ChatMessage

if TYPE_CHECKING:
    from reelforge.adapters.llm import LlmClient

TAG = re.compile(r"\[[a-z][a-z0-9-]*\]")
LATIN = re.compile(r"[A-Za-z]")

SCHEMA = {
    "type": "object",
    "properties": {"devanagari": {"type": "string"}},
    "required": ["devanagari"],
}

SYSTEM = (
    "You convert Hinglish (Hindi written in Latin letters) into Hindi written in Devanagari, "
    "for a text-to-speech engine. Transliterate, never translate: keep every word, the word "
    "order and the punctuation (including '...', '?' and '!'). Write English loanwords as they "
    "are pronounced in Hindi (sorry becomes सॉरी, sir becomes सर, taste becomes टेस्ट). Use the "
    "nukta where Hindi has it (maza becomes मज़ा). Text already in Devanagari stays as it is. "
    'Reply with JSON only: {"devanagari": "..."}.'
)

EXAMPLES: list[tuple[str, str]] = [
    ("Maza nahi aaya!", "मज़ा नहीं आया!"),
    ("Sorry Sir...", "सॉरी सर..."),
    ("Bhaiya... aur milega?", "भैया... और मिलेगा?"),
    ("Sir... ek baar ye taste karo", "सर... एक बार ये टेस्ट करो"),
]


def needs_devanagari(text: str) -> bool:
    """True when the spoken part of `text` has Latin letters (tags are not spoken text)."""
    return bool(LATIN.search(TAG.sub("", text)))


def _messages(text: str) -> list[ChatMessage]:
    msgs: list[ChatMessage] = [{"role": "system", "content": SYSTEM}]
    for roman, deva in EXAMPLES:
        msgs.append({"role": "user", "content": roman})
        msgs.append(
            {"role": "assistant", "content": json.dumps({"devanagari": deva}, ensure_ascii=False)}
        )
    msgs.append({"role": "user", "content": text})
    return msgs


async def to_devanagari(llm: LlmClient, text: str) -> str:
    """Return `text` in Devanagari; on any failure return it unchanged (the worker still guards)."""
    if not needs_devanagari(text):
        return text
    # Convert the spoken pieces between tags one by one so the tags survive exactly.
    out: list[str] = []
    last = 0
    for m in TAG.finditer(text):
        out.append(await _convert(llm, text[last : m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(await _convert(llm, text[last:]))
    return "".join(out)


async def _convert(llm: LlmClient, piece: str) -> str:
    core = piece.strip()
    if not core or not LATIN.search(core):
        return piece
    try:
        reply = await llm.chat(_messages(core), schema=SCHEMA, temperature=0.2)
        converted = str(json.loads(reply)["devanagari"]).strip()
    except Exception:  # noqa: BLE001 - never block a voice on the converter
        return piece
    if not converted or LATIN.search(converted):
        return piece
    lead = piece[: len(piece) - len(piece.lstrip())]
    trail = piece[len(piece.rstrip()) :]
    return f"{lead}{converted}{trail}"
