"""Pick the image adapter for the cast stage and report its status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx

from reelforge.adapters._net import probe
from reelforge.adapters.base import Adapter, AdapterError
from reelforge.adapters.drawthings import DrawThingsAdapter, port_of
from reelforge.adapters.mflux import MfluxAdapter

if TYPE_CHECKING:
    from reelforge.config import Settings
    from reelforge.context import AppContext

MFLUX_MISSING = "mflux isn't set up. Choose mflux in Settings and set its command."


@dataclass(frozen=True)
class BackendStatus:
    kind: Literal["mock", "draw_things"]
    reachable: bool
    port: int
    mflux_available: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reachable": self.reachable,
            "port": self.port,
            "mflux_available": self.mflux_available,
        }


def mflux_configured(settings: Settings) -> bool:
    return settings.image_fallback == "mflux" and settings.mflux_command is not None


def _reachable(url: str) -> bool:
    try:
        probe(url)
    except (ValueError, httpx.HTTPError):
        return False
    return True


async def probe_backend(ctx: AppContext) -> BackendStatus:
    settings = ctx.settings
    port = port_of(settings.drawthings_url)
    if settings.backend == "mock":
        return BackendStatus("mock", True, port, mflux_configured(settings))
    up = await asyncio.to_thread(_reachable, settings.drawthings_url)
    return BackendStatus("draw_things", up, port, mflux_configured(settings))


async def resolve_image_adapter(ctx: AppContext, backend: str | None = None) -> Adapter:
    """The mock adapter on the mock backend; otherwise Draw Things, or mflux when asked for
    (or selected in Settings while Draw Things is down)."""
    settings = ctx.settings
    if settings.backend == "mock":
        return ctx.adapter
    timeout = settings.command_timeout_s

    def mflux() -> Adapter:
        if not mflux_configured(settings) or settings.mflux_command is None:
            raise AdapterError(MFLUX_MISSING)
        return MfluxAdapter(settings.mflux_command, timeout_s=timeout)

    def draw_things() -> Adapter:
        return DrawThingsAdapter(settings.drawthings_url, timeout_s=timeout)

    if backend == "mflux":
        return mflux()
    if backend == "draw_things":
        return draw_things()
    if mflux_configured(settings) and not await asyncio.to_thread(
        _reachable, settings.drawthings_url
    ):
        return mflux()
    return draw_things()
