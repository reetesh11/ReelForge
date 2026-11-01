import asyncio

from _helpers import make_store

from reelforge.jobs.lease import GpuLease
from reelforge.jobs.preflight import preflight


def test_preflight_reason_unload_first_and_wait():
    order: list[str] = []

    async def unload():
        order.append("unload")

    def low():
        order.append("measure")
        return 3.04

    r = asyncio.run(preflight(12.0, available_gb=low, unload_ollama=unload, wait_s=0))
    assert not r.ok and r.reason == "Only 3.0 GB free, job needs 12.0 GB."
    assert order[0] == "unload" and order.count("unload") == 1

    readings = iter([1.0, 1.0, 50.0])
    seen: list[str] = []
    r2 = asyncio.run(
        preflight(
            8.0,
            available_gb=lambda: next(readings),
            unload_ollama=unload,
            wait_s=5,
            poll_s=0.01,
            on_wait=seen.append,
        )
    )
    assert r2.ok and seen[0] == "Only 1.0 GB free, job needs 8.0 GB."


def test_lease_hold_and_release(tmp_path):
    _root, sf, _store, _pid, engine = make_store(tmp_path)
    lease = GpuLease(sf)

    async def go():
        async with lease.hold("a"):
            assert lease.holder() == "a"
        assert lease.holder() is None
        try:
            async with lease.hold("b"):
                raise RuntimeError
        except RuntimeError:
            pass
        assert lease.holder() is None

    asyncio.run(go())
    engine.dispose()
