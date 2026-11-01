"""LLM client protocol used by the story stage."""

from __future__ import annotations

from typing import Any, Protocol

ChatMessage = dict[str, str]


class LlmClient(Protocol):
    name: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any],
        temperature: float = 0.3,
        heavy_next: bool = False,
    ) -> str:
        """Return the raw model text (JSON expected, constrained by `schema`)."""
        ...
