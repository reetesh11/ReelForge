"""OllamaAdapter.chat and health against a stub transport."""

from __future__ import annotations

import json

import httpx
import pytest

from reelforge.adapters.base import AdapterError
from reelforge.adapters.mock_llm import MockLlm
from reelforge.adapters.ollama import OllamaAdapter
from reelforge.models_registry import load_models

URL = "http://127.0.0.1:11434"


def _adapter(handler, model: str | None = "qwen3:8b") -> OllamaAdapter:
    return OllamaAdapter(URL, model, transport=httpx.MockTransport(handler))


def _ok(seen: list[httpx.Request]):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    return handler


async def test_request_shape_and_model_from_registry():
    from reelforge.config import PACKAGED_MODELS

    model = load_models(PACKAGED_MODELS).get("llm").id
    seen: list[httpx.Request] = []
    out = await _adapter(_ok(seen), model).chat(
        [{"role": "user", "content": "x"}], schema={"type": "object"}
    )
    assert out == "{}"
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/chat"
    assert body["model"] == model and body["format"] == {"type": "object"}
    assert body["stream"] is False and body["keep_alive"] == "5m"


async def test_keep_alive_zero_when_heavy_next():
    seen: list[httpx.Request] = []
    await _adapter(_ok(seen)).chat([], schema={}, heavy_next=True)
    assert json.loads(seen[0].content)["keep_alive"] == 0


@pytest.mark.parametrize("t", [0.19, 0.41])
async def test_temperature_range(t):
    with pytest.raises(ValueError):
        await _adapter(_ok([])).chat([], schema={}, temperature=t)


async def test_errors_and_health():
    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no")

    with pytest.raises(AdapterError, match="isn't reachable on port 11434"):
        await _adapter(down).chat([], schema={})
    rep = await _adapter(down).health()
    assert not rep.ok and rep.fix == "Start Ollama: ollama serve"

    def tags(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "other"}]})

    rep = await _adapter(tags).health()
    assert rep.detail == "qwen3:8b isn't pulled." and rep.fix == "ollama pull qwen3:8b"


async def test_mock_llm_responses_repeat_last():
    llm = MockLlm(responses=["a", "b"])
    got = [await llm.chat([{"role": "user", "content": "x"}], schema={}) for _ in range(3)]
    assert got == ["a", "b", "b"] and len(llm.calls) == 3
