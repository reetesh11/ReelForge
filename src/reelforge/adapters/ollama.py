"""Ollama adapter: health check, chat with a JSON schema, and model unload."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from reelforge.adapters._net import PROBE_TIMEOUT_S, is_loopback_url, probe
from reelforge.adapters.base import AdapterError, HealthReport
from reelforge.adapters.llm import ChatMessage

CHAT_TIMEOUT_S = 600.0
MIN_TEMPERATURE = 0.2
MAX_TEMPERATURE = 0.4
DEFAULT_PORT = 11434


class OllamaAdapter:
    name = "ollama"

    def __init__(
        self,
        url: str,
        model: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self.model = model
        self.transport = transport

    @property
    def port(self) -> int:
        return urlparse(self.url).port or DEFAULT_PORT

    def _unreachable(self) -> str:
        return f"Ollama isn't reachable on port {self.port}."

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

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport,
            timeout=timeout,
            trust_env=False,
            base_url=self.url.rstrip("/"),
        )

    async def health(self) -> HealthReport:
        if not is_loopback_url(self.url):
            return HealthReport(
                name=self.name, ok=False, detail=f"{self.url} is not a loopback address"
            )
        try:
            async with self._client(PROBE_TIMEOUT_S) as client:
                resp = await client.get("/api/tags")
            models = [str(m.get("name")) for m in resp.json().get("models", [])]
        except (httpx.HTTPError, ValueError, AttributeError):
            return HealthReport(
                name=self.name,
                ok=False,
                detail=self._unreachable(),
                fix="Start Ollama: ollama serve",
            )
        if self.model is not None and self.model not in models:
            return HealthReport(
                name=self.name,
                ok=False,
                detail=f"{self.model} isn't pulled.",
                fix=f"ollama pull {self.model}",
            )
        return HealthReport(name=self.name, ok=True, detail=f"Ollama reachable at {self.url}")

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any],
        temperature: float = 0.3,
        heavy_next: bool = False,
    ) -> str:
        if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
            raise ValueError(f"temperature must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}")
        if not is_loopback_url(self.url):
            raise AdapterError(f"{self.url} is not a loopback address; refusing to connect")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": temperature},
            "keep_alive": 0 if heavy_next else "5m",
        }
        try:
            async with self._client(CHAT_TIMEOUT_S) as client:
                resp = await client.post("/api/chat", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise AdapterError(self._unreachable()) from None
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ollama request failed: {type(exc).__name__}") from None
        if resp.status_code == 404 and self.model and self.model in resp.text:
            raise AdapterError(f"{self.model} isn't pulled.")
        if resp.status_code >= 400:
            raise AdapterError(f"Ollama returned HTTP {resp.status_code}.")
        try:
            return str(resp.json()["message"]["content"])
        except (ValueError, KeyError, TypeError):
            raise AdapterError("Ollama returned an unexpected reply.") from None

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
