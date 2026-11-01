"""Draw Things adapter (M1: reachability check on loopback only)."""

from __future__ import annotations

import asyncio

import httpx

from reelforge.adapters._net import probe
from reelforge.adapters.base import HealthReport


class DrawThingsAdapter:
    name = "draw_things"

    def __init__(self, url: str) -> None:
        self.url = url

    def check(self) -> HealthReport:
        try:
            resp = probe(self.url)
        except ValueError as exc:
            return HealthReport(name=self.name, ok=False, detail=str(exc))
        except httpx.HTTPError:
            return HealthReport(
                name=self.name, ok=False, detail=f"Draw Things is not reachable at {self.url}"
            )
        return HealthReport(
            name=self.name,
            ok=True,
            detail=f"Draw Things reachable at {self.url} (HTTP {resp.status_code})",
        )

    async def health(self) -> HealthReport:
        return await asyncio.to_thread(self.check)
