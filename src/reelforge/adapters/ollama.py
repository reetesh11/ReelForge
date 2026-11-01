"""Ollama adapter (M1: health check and model unload)."""

from __future__ import annotations

import asyncio

import httpx

from reelforge.adapters._net import PROBE_TIMEOUT_S, is_loopback_url, probe
from reelforge.adapters.base import HealthReport


class OllamaAdapter:
    name = "ollama"

    def __init__(self, url: str, model: str | None = None) -> None:
        self.url = url
        self.model = model

    def check(self) -> HealthReport:
        try:
            resp = probe(self.url, "/api/version")
        except ValueError as exc:
            return HealthReport(name=self.name, ok=False, detail=str(exc))
        except httpx.HTTPError:
            return HealthReport(
                name=self.name, ok=False, detail=f"Ollama is not running at {self.url}"
            )
        version: str | None = None
        try:
            version = str(resp.json().get("version"))
        except (ValueError, AttributeError):
            version = None
        return HealthReport(
            name=self.name,
            ok=True,
            version=version,
            detail=f"Ollama {version or ''} reachable at {self.url}".replace("  ", " "),
        )

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)

    def _unload_sync(self) -> None:
        if self.model is None or not is_loopback_url(self.url):
            return
        try:
            httpx.post(
                self.url.rstrip("/") + "/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=PROBE_TIMEOUT_S,
                trust_env=False,
            )
        except (httpx.HTTPError, OSError):
            return

    async def unload(self) -> None:
        await asyncio.to_thread(self._unload_sync)
