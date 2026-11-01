"""WebSocket event stream."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from reelforge.context import AppContext
from reelforge.events import Event


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/events")
    async def events(ws: WebSocket) -> None:
        queue = ctx.bus.subscribe()
        await ws.accept()
        receiver = asyncio.create_task(ws.receive_text())
        try:
            while True:
                getter: asyncio.Task[Event] = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                if receiver in done:
                    getter.cancel()
                    if receiver.exception() is not None:
                        return
                    receiver = asyncio.create_task(ws.receive_text())
                    if getter.cancelled() or not getter.done():
                        continue
                if getter in done:
                    event = getter.result()
                    await ws.send_json({"type": event.type, "data": event.data})
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            ctx.bus.unsubscribe(queue)
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await receiver

    return router
