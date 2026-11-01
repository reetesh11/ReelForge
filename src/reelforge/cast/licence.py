"""Image model licence warning (pure function over a registry entry)."""

from __future__ import annotations

from reelforge.models_registry import ModelEntry

_NON_COMMERCIAL_MARKERS = ("non-commercial", "noncommercial", "non commercial", "-nc")


def licence_warning(entry: ModelEntry) -> str | None:
    if not entry.license.strip():
        return f"Image model licence is not filled in. Check {entry.id} before commercial use."
    lowered = entry.license.lower()
    if any(marker in lowered for marker in _NON_COMMERCIAL_MARKERS):
        return (
            f"Image model licence: {entry.license} - not for commercial use. "
            f"See {entry.license_url}."
        )
    return None
