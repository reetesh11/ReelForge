"""AC-7: memory pre-flight, Ollama unload first, single GPU lease."""

from __future__ import annotations

import threading
import time

from rf_helpers import (
    CountingAdapter,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    run_async,
    submit,
    wait_job,
)


def test_preflight_ok_when_enough_memory():
    from reelforge.jobs.preflight import preflight

    async def unload():
        pass

    r = run_async(
        preflight(8.0, available_gb=lambda: 20.0, unload_ollama=unload, wait_s=0)
    )
    assert r.ok and r.reason is None and r.free_gb == 20.0 and r.need_gb == 8.0


def test_preflight_fails_with_exact_reason_and_unloads_first():
    from reelforge.jobs.preflight import preflight

    order: list[str] = []

    async def unload():
        order.append("unload")

    def avail():
        order.append("measure")
        return 3.04

    r = run_async(preflight(12.0, available_gb=avail, unload_ollama=unload, wait_s=0))
    assert not r.ok
    assert r.reason == "Only 3.0 GB free, job needs 12.0 GB."
    assert order[0] == "unload" and order.count("unload") == 1 and "measure" in order


def test_preflight_waits_until_memory_frees_up():
    from reelforge.jobs.preflight import preflight

    readings = iter([2.0, 2.0, 30.0, 30.0, 30.0])
    waits: list[str] = []

    async def unload():
        pass

    r = run_async(
        preflight(
            8.0,
            available_gb=lambda: next(readings),
            unload_ollama=unload,
            wait_s=5.0,
            poll_s=0.01,
            on_wait=waits.append,
        )
    )
    assert r.ok
    assert waits and waits[0] == "Only 2.0 GB free, job needs 8.0 GB."


def test_preflight_gives_up_after_wait_s():
    from reelforge.jobs.preflight import preflight

    async def unload():
        pass

    t0 = time.monotonic()
    r = run_async(
        preflight(
            8.0, available_gb=lambda: 1.0, unload_ollama=unload, wait_s=0.3, poll_s=0.05
        )
    )
    assert not r.ok and 0.25 <= time.monotonic() - t0 < 5


def test_job_does_not_start_when_memory_is_insufficient(tmp_path):
    settings = make_settings(tmp_path, preflight_wait_s=0.0)
    adapter = CountingAdapter(settings)
    unloads: list[int] = []

    async def unload():
        unloads.append(1)

    ctx = make_ctx(settings, adapter=adapter, available_gb=1.0, unload=unload)
    reason = "Only 1.0 GB free, job needs 8.0 GB."
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, heavy=True, mem_need_gb=8.0)["job_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = ctx.queue.get(job_id)
            assert job.status != "running"
            assert ctx.lease.holder() is None
            if reason in (job.message or "") or reason in (job.error or ""):
                break
            time.sleep(0.05)
        job = ctx.queue.get(job_id)
        assert job.status in {"queued", "failed"}
        assert reason in (job.message or "") or reason in (job.error or "")
    assert adapter.runs == 0
    assert unloads, "ollama must be unloaded before the pre-flight"
    ctx.close()


def test_two_heavy_jobs_never_hold_the_lease_together(tmp_path):
    settings = make_settings(tmp_path)
    ctx = make_ctx(settings, adapter=CountingAdapter(settings))
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        ids = [
            submit(
                client,
                pid,
                owner_id=f"h{i}",
                seed=i,
                heavy=True,
                mem_need_gb=0.5,
                params={"mock": {"sleep_s": 0.8}},
            )["job_id"]
            for i in (1, 2)
        ]
        max_running = 0
        holders: set[str] = set()
        stop = threading.Event()

        def sample():
            nonlocal max_running
            while not stop.is_set():
                running = [i for i in ids if ctx.queue.get(i).status == "running"]
                max_running = max(max_running, len(running))
                h = ctx.lease.holder()
                if h:
                    holders.add(h)
                    assert h in ids
                time.sleep(0.01)

        t = threading.Thread(target=sample, daemon=True)
        t.start()
        for i in ids:
            assert (
                wait_job(ctx, i, {"succeeded", "failed"}, timeout=40).status
                == "succeeded"
            )
        stop.set()
        t.join(5)
    assert max_running == 1
    assert holders == set(ids)
    assert ctx.lease.holder() is None
    ctx.close()


def test_lease_hold_records_holder_and_releases_on_error(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))

    async def go():
        async with ctx.lease.hold("job-a"):
            assert ctx.lease.holder() == "job-a"
        assert ctx.lease.holder() is None
        try:
            async with ctx.lease.hold("job-b"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert ctx.lease.holder() is None

    run_async(go())
    ctx.close()
