"""Deterministic LLM for tests and the mock backend. Makes no network access."""

from __future__ import annotations

import json
from typing import Any

from reelforge.adapters.llm import ChatMessage


def canned_story() -> dict[str, Any]:
    scenes: list[dict[str, Any]] = [
        {
            "id": "s1",
            "setting": "Indian wedding mandap at night",
            "action": "Aloo bursts in through the crowd, panting",
            "framing": "wide",
            "duration": 2.0,
        },
        {
            "id": "s2",
            "speaker": "tomato",
            "line": "Arre Aloo, itni der kyun?",
            "action": "Tamatar crosses his arms, annoyed",
            "framing": "closeup",
            "duration": 2.0,
        },
        {
            "id": "s3",
            "speaker": "potato",
            "line": "Mithai ke bina shaadi?",
            "action": "Aloo proudly lifts the box",
            "framing": "closeup",
            "duration": 2.0,
        },
        {
            "id": "s4",
            "action": "Guests rush toward the box, cheering",
            "framing": "medium",
            "continue_from": "s3",
            "duration": 2.0,
        },
        {
            "id": "s5",
            "action": "Both characters wink at camera",
            "framing": "medium",
            "duration": 2.0,
            "end_card": True,
        },
    ]
    return {
        "version": 1,
        "title": "Wedding thekua rescue",
        "language": "hinglish",
        "style": "3D Pixar-style cartoon, warm festive lighting",
        "aspect": "9:16",
        "fps": 24,
        "target_seconds": 12,
        "characters": {
            "tomato": {
                "name": "Tamatar",
                "look": "round glossy red tomato, big expressive eyes, tiny green leaf hat",
            },
            "potato": {
                "name": "Aloo",
                "look": "chubby brown potato, bushy black moustache, pink turban, white kurta",
            },
        },
        "scenes": scenes,
    }


def _canned_bible_line(messages: list[ChatMessage]) -> str:
    fields: dict[str, str] = {}
    for line in messages[-1]["content"].splitlines():
        label, _, value = line.partition(": ")
        fields[label] = value
    name = fields.get("Character name", "")
    look = fields.get("Look", "").rstrip(".")
    return f"Character: {name}. Look: {look}."


class MockLlm:
    name = "mock-llm"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any],
        temperature: float = 0.3,
        heavy_next: bool = False,
    ) -> str:
        self.calls.append([dict(m) for m in messages])
        if "bible_line" in schema.get("properties", {}):
            return json.dumps({"bible_line": _canned_bible_line(messages)})
        if not self.responses:
            return json.dumps({"story": canned_story(), "questions": []})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]
