"""Versioned prompt files shipped with the package."""

from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
STRUCTURE_PROMPT = "structure.v1.md"
REPAIR_PROMPT = "repair.v1.md"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")
