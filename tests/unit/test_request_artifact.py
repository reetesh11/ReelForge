import asyncio

from _helpers import make_ctx

from reelforge.artifacts.service import ArtifactRequest, request_artifact
from reelforge.db.models import Project


def test_second_identical_request_is_a_cache_hit(tmp_path):
    ctx = make_ctx(tmp_path)
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/t")
        s.add(p)
        s.flush()
        pid = p.id
    req = ArtifactRequest(
        project_id=pid, owner_type="c", owner_id="o", kind="candidate", media="image",
        prompt="p", seed=1,
    )  # fmt: skip

    async def go():
        first = request_artifact(ctx, req)
        assert not first.cache_hit and first.job is not None
        await ctx.worker.start()
        await ctx.worker.wait_idle(30)
        await ctx.worker.stop()

    asyncio.run(go())
    second = request_artifact(ctx, req)
    assert second.cache_hit and second.job is None and second.artifact is not None
    assert len(ctx.queue.list()) == 1
    ctx.close()
