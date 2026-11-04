"""Pick the video adapter for the shots stage and report its status."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from reelforge.adapters.base import Adapter
from reelforge.adapters.ltx import LtxAdapter

if TYPE_CHECKING:
    from reelforge.context import AppContext

ENGINE_DOWN = "Video engine check failed - see Settings & status"


def ltx_adapter(ctx: AppContext) -> LtxAdapter:
    s = ctx.settings
    return LtxAdapter(s.ltx_path, timeout_s=s.shot_timeout_s, sample_interval_s=s.sample_interval_s)


async def resolve_video_adapter(ctx: AppContext) -> Adapter:
    """The mock adapter on the mock backend, otherwise the real ltx-2-mlx adapter."""
    if ctx.settings.backend == "mock":
        return ctx.adapter
    return ltx_adapter(ctx)


def engine_status(ctx: AppContext) -> tuple[bool, str]:
    """(ok, message). The mock backend is always ok; the real one runs the flag check."""
    if ctx.settings.backend == "mock":
        return True, ""
    report = ltx_adapter(ctx).check()
    return (True, "") if report.ok else (False, ENGINE_DOWN)


async def engine_status_async(ctx: AppContext) -> tuple[bool, str]:
    return await asyncio.to_thread(engine_status, ctx)
