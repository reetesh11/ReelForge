"""AC-6: cancel, one automatic retry, then failed."""

from __future__ import annotations

import time

import pytest
from rf_helpers import (
    CountingAdapter,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    submit,
    wait_job,
)


def _ctx(tmp_path, **kw):
    settings = make_settings(tmp_path)
    adapter = CountingAdapter(settings)
    return make_ctx(settings, adapter=adapter, **kw), adapter


def test_cancel_running_job_stops_child_and_marks_cancelled(tmp_path):
    import psutil

    ctx, _ = _ctx(tmp_path)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"sleep_s": 60}})["job_id"]
        running = wait_job(ctx, job_id, {"running"})
        assert running.pid and psutil.pid_exists(running.pid)
        ctx.queue.cancel(job_id)
        done = wait_job(ctx, job_id, {"cancelled", "succeeded", "failed"}, timeout=20)
        assert done.status == "cancelled"
        deadline = time.monotonic() + 10
        while psutil.pid_exists(running.pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not psutil.pid_exists(running.pid)
    ctx.close()


def test_cancel_queued_job_is_immediate_and_finished_jobs_reject_cancel(tmp_path):
    from reelforge.jobs.queue import JobStateError

    ctx, _ = _ctx(tmp_path)
    job = ctx.queue.enqueue(type="artifact.generate")
    assert job.status == "queued" and job.attempts == 0 and job.progress == 0
    assert ctx.queue.cancel(job.id).status == "cancelled"
    with pytest.raises(JobStateError):
        ctx.queue.cancel(job.id)
    with pytest.raises(JobStateError):
        ctx.queue.retry(job.id)
    ctx.close()


def test_queue_get_unknown_raises(tmp_path):
    from reelforge.jobs.queue import JobNotFound

    ctx, _ = _ctx(tmp_path)
    with pytest.raises(JobNotFound):
        ctx.queue.get("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    ctx.close()


def test_transient_failure_is_retried_once_then_succeeds(tmp_path):
    ctx, adapter = _ctx(tmp_path)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"transient_failures": 1}})[
            "job_id"
        ]
        job = wait_job(ctx, job_id, {"succeeded", "failed"})
    assert job.status == "succeeded" and job.progress == 100 and job.exit_code == 0
    assert adapter.runs == 2
    ctx.close()


def test_persistent_transient_failure_fails_after_exactly_two_attempts(tmp_path):
    ctx, adapter = _ctx(tmp_path)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"transient_failures": 10}})[
            "job_id"
        ]
        job = wait_job(ctx, job_id, {"succeeded", "failed"})
        time.sleep(0.5)  # a third attempt would show up here
    assert job.status == "failed" and job.error
    assert ctx.queue.get(job_id).attempts == 2
    assert adapter.runs == 2
    ctx.close()


def test_non_transient_failure_is_not_retried(tmp_path):
    ctx, adapter = _ctx(tmp_path)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"fail": "bad prompt"}})["job_id"]
        job = wait_job(ctx, job_id, {"succeeded", "failed"})
    assert job.status == "failed" and "bad prompt" in job.error
    assert adapter.runs == 1
    ctx.close()


def test_nonzero_exit_code_and_unknown_job_type(tmp_path):
    ctx, _ = _ctx(tmp_path)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"exit_code": 3}})["job_id"]
        job = wait_job(ctx, job_id, {"succeeded", "failed"})
        assert job.status == "failed" and job.error == "exit code 3"
        weird = ctx.queue.enqueue(type="no.such.type")
        weird = wait_job(ctx, weird.id, {"succeeded", "failed"})
        assert weird.status == "failed" and weird.error == "unknown job type"
    ctx.close()


def test_retry_resets_a_failed_job(tmp_path):
    from reelforge.db.models import Job
    from sqlalchemy import update

    ctx, _ = _ctx(tmp_path)
    job = ctx.queue.enqueue(type="artifact.generate")
    with ctx.session_factory() as s, s.begin():
        s.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(status="failed", error="boom", attempts=2, progress=40)
        )
    r = ctx.queue.retry(job.id)
    assert (
        r.status == "queued" and r.attempts == 0 and r.error is None and r.progress == 0
    )
    ctx.close()
