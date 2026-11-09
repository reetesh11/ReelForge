"""Model registry: the only place model IDs are read from (models.toml)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

COMMERCIAL_LICENCES = (
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "CC0-1.0",
    "Unlicense",
)
AUDIO_PREFIX = "audio_"


class ModelLicenceError(ValueError):
    """An audio model whose licence is empty or not on the commercial list."""


class ModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    id: str
    revision: str
    license: str = ""
    license_url: str = ""
    steps: int | None = Field(default=None, gt=0)
    max_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class ModelRegistry:
    def __init__(self, entries: list[ModelEntry]) -> None:
        self._entries = {e.key: e for e in entries}

    def get(self, key: str) -> ModelEntry:
        return self._entries[key]

    def keys(self) -> list[str]:
        return list(self._entries)

    def entries(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def missing_license(self) -> list[str]:
        return [e.key for e in self._entries.values() if not e.license]


def check_audio_licences(entries: list[ModelEntry]) -> None:
    """Raise ModelLicenceError when an `audio_*` entry has an empty or non-commercial licence."""
    allowed = {name.lower() for name in COMMERCIAL_LICENCES}
    for entry in entries:
        if not entry.key.startswith(AUDIO_PREFIX):
            continue
        licence = entry.license.strip()
        if not licence:
            raise ModelLicenceError(f"Audio model {entry.key} has no licence in models.toml.")
        if licence.lower() not in allowed:
            raise ModelLicenceError(
                f"Audio model {entry.key} has licence {entry.license}, which is not on the "
                f"commercial list ({', '.join(COMMERCIAL_LICENCES)})."
            )


def load_models(path: Path) -> ModelRegistry:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    table = data.get("models", {})
    entries = [ModelEntry(key=key, **body) for key, body in table.items()]
    check_audio_licences(entries)
    return ModelRegistry(entries)
