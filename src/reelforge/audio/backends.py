"""Pick the sound adapter and report whether the engine can run."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reelforge.context import AppContext

ENGINE_DOWN = "Sound engine is not available - see Settings & status"


def engine_status(ctx: AppContext) -> tuple[bool, str]:
    """(ok, message). The mock backend is always ok."""
    if ctx.settings.backend == "mock":
        return True, ""
    return False, ENGINE_DOWN


async def engine_status_async(ctx: AppContext) -> tuple[bool, str]:
    return await asyncio.to_thread(engine_status, ctx)
