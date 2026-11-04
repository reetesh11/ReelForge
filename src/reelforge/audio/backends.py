"""Pick the sound adapter and report whether the engine can run."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from reelforge.adapters.base import Adapter, AdapterError

if TYPE_CHECKING:
    from reelforge.context import AppContext
    from reelforge.models_registry import ModelEntry

ENGINE_DOWN = "Sound engine is not available - see Settings & status"
STUB_KEY = "audio_stub"


def model_for(ctx: AppContext, kind: str) -> ModelEntry:
    """The registry entry that renders `kind` (`audio_<kind>`, else the placeholder)."""
    for key in (f"audio_{kind}", STUB_KEY):
        if key in ctx.registry.keys():
            return ctx.registry.get(key)
    raise AdapterError("No sound model is listed in models.toml.")


async def resolve_audio_adapter(ctx: AppContext) -> Adapter:
    """The mock adapter on the mock backend; real adapters arrive with the model choice."""
    if ctx.settings.backend == "mock":
        return ctx.adapter
    raise AdapterError(ENGINE_DOWN)


def engine_status(ctx: AppContext) -> tuple[bool, str]:
    """(ok, message). The mock backend is always ok."""
    if ctx.settings.backend == "mock":
        return True, ""
    return False, ENGINE_DOWN


async def engine_status_async(ctx: AppContext) -> tuple[bool, str]:
    return await asyncio.to_thread(engine_status, ctx)
