"""In-process event bus feeding the WebSocket endpoint."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=lambda: {})


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[tuple[asyncio.Queue[Event], asyncio.AbstractEventLoop | None]] = []

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            self._subs.append((queue, loop))
        return queue

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        with self._lock:
            self._subs = [(s, loop) for s, loop in self._subs if s is not q]

    def publish(self, type: str, data: dict[str, Any]) -> None:
        event = Event(type=type, data=dict(data))
        with self._lock:
            subs = list(self._subs)
        for queue, loop in subs:
            if loop is None:
                queue.put_nowait(event)
                continue
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                self.unsubscribe(queue)
