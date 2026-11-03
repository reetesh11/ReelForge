"""Implementation tests: GENERATE_MEM_GB is gone from src."""

from __future__ import annotations

from pathlib import Path


def test_generate_mem_gb_removed() -> None:
    src = Path(__file__).resolve().parents[2] / "src"
    assert all("GENERATE_MEM_GB" not in p.read_text() for p in src.rglob("*.py"))
