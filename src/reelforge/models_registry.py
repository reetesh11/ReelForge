"""Model registry: the only place model IDs are read from (models.toml)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    id: str
    revision: str
    license: str = ""
    license_url: str = ""


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


def load_models(path: Path) -> ModelRegistry:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    table = data.get("models", {})
    entries = [ModelEntry(key=key, **body) for key, body in table.items()]
    return ModelRegistry(entries)
