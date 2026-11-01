import asyncio
import threading

from reelforge.events import EventBus


def test_publish_from_other_thread_reaches_subscriber():
    async def go():
        bus = EventBus()
        q = bus.subscribe()
        threading.Thread(target=lambda: bus.publish("job.updated", {"a": 1})).start()
        ev = await asyncio.wait_for(q.get(), 5)
        bus.unsubscribe(q)
        bus.publish("job.updated", {})
        return ev

    ev = asyncio.run(go())
    assert ev.type == "job.updated" and ev.data == {"a": 1}
