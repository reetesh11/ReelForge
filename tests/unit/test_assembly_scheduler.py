"""Preview scheduler (server-side debounce) and the light assemble jobs."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from _helpers import make_ctx, make_store, spec_for

from reelforge.assembly.build import working_edl_path
from reelforge.assembly.edl import Edl, edl_hash, save_edl
from reelforge.assembly.jobs import FINAL_JOB, PREVIEW_JOB
from reelforge.db.models import Project


def _project(ctx) -> str:
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/t", stage="SHOTS_APPROVED")
        s.add(p)
        s.flush()
        return p.id


def _setup(tmp_path: Path, debounce: float = 0.1):
    ctx = make_ctx(tmp_path, preview_debounce_s=debounce)
    pid = _project(ctx)
    edl = Edl(project_id=pid, video=[], dialogue=[], captions=[])
    save_edl(edl, working_edl_path(ctx, pid))
    return ctx, pid, edl


def _previews(ctx, pid):
    return [j for j in ctx.queue.list(project_id=pid) if j.type == PREVIEW_JOB]


def _wait(pred, timeout: float = 5.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met")


def test_burst_of_touches_makes_one_light_job(tmp_path: Path) -> None:
    ctx, pid, edl = _setup(tmp_path)
    for _ in range(4):
        ctx.previews.touch(pid)
    left = ctx.previews.remaining(pid)
    assert left is not None and 0 < left <= 0.1
    assert _previews(ctx, pid) == []
    _wait(lambda: len(_previews(ctx, pid)) == 1)
    time.sleep(0.2)
    (job,) = _previews(ctx, pid)
    assert job.heavy is False and job.mem_need_gb == 0
    assert job.payload == {"stage": "assembly", "kind": "preview", "edl_hash": edl_hash(edl)}
    assert ctx.previews.remaining(pid) is None
    assert (working_edl_path(ctx, pid).parent / "edls" / f"{edl_hash(edl)}.json").is_file()
    assert not [j for j in ctx.queue.list(project_id=pid) if j.type == FINAL_JOB]
    ctx.close()


def test_touch_during_a_running_job_queues_exactly_one_more(tmp_path: Path) -> None:
    ctx, pid, _ = _setup(tmp_path, debounce=0.05)
    first = ctx.previews.enqueue_now(pid)
    assert ctx.queue.transition(first.id, "queued", status="running")
    ctx.previews.touch(pid)
    ctx.previews.touch(pid)
    _wait(lambda: len(_previews(ctx, pid)) == 2)
    time.sleep(0.2)
    jobs = _previews(ctx, pid)
    assert len(jobs) == 2
    assert ctx.queue.get(first.id).status == "running"
    assert sorted(j.status for j in jobs) == ["queued", "running"]
    ctx.close()


def test_a_queued_preview_is_replaced(tmp_path: Path) -> None:
    ctx, pid, _ = _setup(tmp_path)
    first = ctx.previews.enqueue_now(pid)
    second = ctx.previews.enqueue_now(pid)
    assert ctx.queue.get(first.id).status == "cancelled"
    assert ctx.queue.get(second.id).status == "queued"
    ctx.close()


def test_enqueue_without_an_edl_fails_cleanly(tmp_path: Path) -> None:
    from reelforge.assembly.state import AssemblyError

    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    with pytest.raises(AssemblyError) as exc:
        ctx.previews.enqueue_now(pid)
    assert exc.value.status == 404
    ctx.close()


def test_preview_handler_is_registered() -> None:
    from reelforge.jobs.worker import HANDLERS

    assert PREVIEW_JOB in HANDLERS


def test_register_in_place_keeps_the_file_where_it_is(tmp_path: Path) -> None:
    root, _sf, store, pid, engine = make_store(tmp_path)
    folder = root / "projects/2026-01-01_t_x/assembly"
    folder.mkdir(parents=True)
    f = folder / "final.mp4"
    f.write_bytes(b"abc")
    first = store.register_in_place(spec_for(pid, kind="final", subdir="assembly"), f)
    other = folder / "cover.jpg"
    other.write_bytes(b"jpg")
    second = store.register_in_place(spec_for(pid, kind="final", subdir="assembly"), other)
    assert f.read_bytes() == b"abc" and not (folder / "final.json").exists()
    assert first.path == "projects/2026-01-01_t_x/assembly/final.mp4"
    assert (first.take_no, second.take_no) == (1, 2)
    assert first.is_active and second.is_active
    with pytest.raises(ValueError):
        store.register_in_place(spec_for(pid), tmp_path / "outside.bin")
    engine.dispose()
