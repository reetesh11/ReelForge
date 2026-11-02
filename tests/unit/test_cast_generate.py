"""cast.generate handler, driven by enqueuing jobs directly (no cast routes needed)."""

from __future__ import annotations

import time
from typing import Any

import yaml_samples as ys
from _helpers import make_client, make_ctx

from reelforge.adapters.base import AdapterError
from reelforge.adapters.mock import MockAdapter
from reelforge.adapters.mock_llm import MockLlm
from reelforge.cast import state


class Rec(MockAdapter):
    def __init__(self, ctx: Any) -> None:
        super().__init__(ctx.registry, default_timeout_s=30, sample_interval_s=0.1)
        self.seeds: list[int] = []
        self.prompts: list[str] = []
        self.fail_on: int | None = None
        self.after: Any = None

    async def run(self, task, out_dir, progress, cancel, *, ctx_job_id=None):  # type: ignore[override]
        self.seeds.append(task.seed)
        self.prompts.append(task.prompt)
        if self.fail_on == len(self.seeds):
            raise AdapterError("boom")
        res = await super().run(task, out_dir, progress, cancel, ctx_job_id=ctx_job_id)
        if self.after:
            self.after(len(self.seeds), ctx_job_id)
        return res


def _world(tmp_path, llm=None):
    ctx = make_ctx(tmp_path)
    if llm is not None:
        ctx.llm = llm
    adapter = Rec(ctx)
    ctx.adapter = adapter
    client = make_client(ctx)
    return ctx, client, adapter


def _project(client) -> str:
    pid = client.post("/api/v1/projects", json={"title": "T"}).json()["id"]
    r = client.put(
        f"/api/v1/projects/{pid}/story",
        content=ys.STORY.encode(),
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200
    return pid


def _run(ctx, pid: str, **payload: Any):
    job = ctx.queue.enqueue(
        type=state.GENERATE_JOB,
        project_id=pid,
        payload={"key": "tomato", "stage": "cast", **payload},
        heavy=True,
        mem_need_gb=10.0,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        cur = ctx.queue.get(job.id)
        if cur.status in {"succeeded", "failed", "cancelled"}:
            return cur
        time.sleep(0.03)
    raise AssertionError("job did not finish")


def test_seeds_cache_and_changed_bible_line(tmp_path):
    ctx, client, ad = _world(tmp_path)
    with client:
        pid = _project(client)
        job = _run(ctx, pid, seed=7)
        assert job.status == "succeeded", job.error
        assert ad.seeds == [7, 8, 9, 10]
        ids = state.get_slot(ctx, pid, "tomato").candidate_ids  # type: ignore[union-attr]
        job2 = _run(ctx, pid, seed=7)
        assert job2.status == "succeeded" and len(ad.seeds) == 4
        assert state.get_slot(ctx, pid, "tomato").candidate_ids == ids  # type: ignore[union-attr]
        state.update_slot(ctx, pid, "tomato", bible_line="a brand new line", bible_source="user")
        assert _run(ctx, pid, seed=7).status == "succeeded"
        assert len(ad.seeds) == 8
        assert all("a brand new line" in p for p in ad.prompts[4:])
        assert all("a brand new line" not in p for p in ad.prompts[:4])


def test_llm_failure_falls_back_to_raw_look(tmp_path):
    class Broken(MockLlm):
        async def chat(self, messages, *, schema, temperature=0.3, heavy_next=False):
            raise RuntimeError("llm down")

    ctx, client, ad = _world(tmp_path, llm=Broken())
    with client:
        pid = _project(client)
        assert _run(ctx, pid, seed=1).status == "succeeded"
        slot = state.get_slot(ctx, pid, "tomato")
        assert slot is not None and slot.bible_source == "raw"
        assert slot.bible_line == "round red tomato, big eyes"
        assert "round red tomato, big eyes" in ad.prompts[0]


def test_mid_run_failure_keeps_finished_images(tmp_path):
    ctx, client, ad = _world(tmp_path)
    ad.fail_on = 3
    with client:
        pid = _project(client)
        job = _run(ctx, pid, seed=1)
        assert job.status == "failed" and job.error == "boom"
        assert len(state.get_slot(ctx, pid, "tomato").candidate_ids) == 2  # type: ignore[union-attr]
        assert job.result is not None and job.result["completed"] == 2


def test_cancel_stops_loop_and_regenerate_continues_seeds(tmp_path):
    ctx, client, ad = _world(tmp_path)

    def cancel_after_two(n, job_id):
        if n == 2:
            ctx.queue.cancel(job_id)

    ad.after = cancel_after_two
    with client:
        pid = _project(client)
        assert _run(ctx, pid, seed=50).status == "cancelled"
        assert ad.seeds == [50, 51]
        ad.after = None
        assert _run(ctx, pid, regenerate=True).status == "succeeded"
        assert ad.seeds[2:] == [54, 55, 56, 57]
