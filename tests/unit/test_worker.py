import asyncio

import pytest
from _helpers import make_ctx

from reelforge.artifacts.service import ArtifactRequest, request_artifact


@pytest.mark.parametrize(
    "hook,final", [({"transient_failures": 1}, "succeeded"), ({}, "succeeded")]
)
def test_worker_runs_job_to_success(tmp_path, hook, final):
    ctx = make_ctx(tmp_path)

    async def go():
        project_id = _project(ctx)
        req = ArtifactRequest(
            project_id=project_id, owner_type="c", owner_id="o", kind="candidate",
            media="image", prompt="p", seed=1, params={"mock": hook},
        )  # fmt: skip
        res = request_artifact(ctx, req)
        await ctx.worker.start()
        await ctx.worker.wait_idle(30)
        await ctx.worker.stop()
        return res.job.id  # type: ignore[union-attr]

    job_id = asyncio.run(go())
    assert ctx.queue.get(job_id).status == final
    ctx.close()


def _project(ctx) -> str:
    from reelforge.db.models import Project

    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/t")
        s.add(p)
        s.flush()
        return p.id


def _run_one(ctx, **kw):
    pid = _project(ctx)
    base = dict(
        project_id=pid, owner_type="c", owner_id="o", kind="candidate", media="image",
        prompt="p", seed=1,
    )  # fmt: skip
    res = request_artifact(ctx, ArtifactRequest(**{**base, **kw}))  # type: ignore[arg-type]

    async def go():
        await ctx.worker.start()
        await ctx.worker.wait_idle(30)
        await ctx.worker.stop()

    asyncio.run(go())
    return ctx.queue.get(res.job.id)  # type: ignore[union-attr]


def test_persistent_transient_failure_stops_after_two_attempts(tmp_path):
    ctx = make_ctx(tmp_path)
    job = _run_one(ctx, params={"mock": {"transient_failures": 5}})
    assert job.status == "failed" and job.attempts == 2 and job.error
    ctx.close()


def test_unknown_job_type_fails(tmp_path):
    ctx = make_ctx(tmp_path)
    job = ctx.queue.enqueue(type="nope")

    async def go():
        await ctx.worker.start()
        await ctx.worker.wait_idle(10)
        await ctx.worker.stop()

    asyncio.run(go())
    assert ctx.queue.get(job.id).error == "unknown job type"
    ctx.close()


def test_heavy_job_with_too_little_memory_fails_with_reason(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.available_gb = lambda: 1.0
    job = _run_one(ctx, heavy=True, mem_need_gb=8.0)
    assert job.status == "failed" and job.error == "Only 1.0 GB free, job needs 8.0 GB."
    assert ctx.lease.holder() is None
    ctx.close()
