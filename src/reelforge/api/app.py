"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reelforge import __version__
from reelforge.api import routes_jobs, routes_media, routes_projects, ws
from reelforge.api.schemas import CheckOut, HealthOut
from reelforge.context import AppContext

log = structlog.get_logger()


async def _health_loop(ctx: AppContext) -> None:
    while True:
        await asyncio.sleep(ctx.settings.health_poll_s)
        try:
            await asyncio.to_thread(ctx.health.poll_once)
        except Exception:  # noqa: BLE001
            log.exception("health.poll_failed")


def create_app(ctx: AppContext, *, start_worker: bool = True) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        poller: asyncio.Task[None] | None = None
        if start_worker:
            await ctx.worker.start()
            poller = asyncio.create_task(_health_loop(ctx))
        try:
            yield
        finally:
            if poller is not None:
                poller.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await poller
            if start_worker:
                await ctx.worker.stop()

    app = FastAPI(title="ReelForge", version=__version__, lifespan=lifespan)
    ui = ctx.settings.ui_port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://127.0.0.1:{ui}", f"http://localhost:{ui}"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health() -> HealthOut:
        report = await asyncio.to_thread(ctx.run_doctor)
        return HealthOut(
            status=report.overall,
            checks=[CheckOut(**c.model_dump()) for c in report.checks],
        )

    app.include_router(routes_projects.build_router(ctx))
    app.include_router(routes_jobs.build_router(ctx))
    app.include_router(routes_media.build_router(ctx))
    app.include_router(ws.build_router(ctx))
    return app
