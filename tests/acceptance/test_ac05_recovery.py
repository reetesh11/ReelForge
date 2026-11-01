"""AC-5: killing the process mid-job; restart returns the job to queued, clears the lease."""

from __future__ import annotations

import sqlite3
import time

from rf_helpers import (
    UpProcess,
    artifacts_of,
    free_port,
    http_json,
    make_ctx,
    make_settings,
)


def test_orphan_recovery_after_hard_kill(tmp_path):
    root = tmp_path / "data"
    port = free_port()
    up = UpProcess(root, port)
    try:
        up.wait_ready()
        _, proj = http_json(
            "POST", f"{up.url}/api/v1/projects", {"title": "Crash tale"}
        )
        pid = proj["id"]
        base = {"owner_type": "character", "media": "image", "prompt": "p"}
        _, done = http_json(
            "POST",
            f"{up.url}/api/v1/projects/{pid}/artifacts",
            {**base, "owner_id": "done", "kind": "candidate", "seed": 1},
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            _, job = http_json("GET", f"{up.url}/api/v1/jobs/{done['job_id']}")
            if job["status"] == "succeeded":
                break
            time.sleep(0.2)
        assert job["status"] == "succeeded"

        _, slow = http_json(
            "POST",
            f"{up.url}/api/v1/projects/{pid}/artifacts",
            {
                **base,
                "owner_id": "slow",
                "kind": "candidate",
                "seed": 2,
                "heavy": True,
                "mem_need_gb": 0.0,
                "params": {"mock": {"sleep_s": 60}},
            },
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            _, job = http_json("GET", f"{up.url}/api/v1/jobs/{slow['job_id']}")
            if job["status"] == "running":
                break
            time.sleep(0.1)
        assert job["status"] == "running"
        up.kill_hard()
    finally:
        up.stop()

    settings = make_settings(tmp_path, data_root=root)
    ctx = make_ctx(settings)
    sha_before = {a.id: a.sha256 for a in artifacts_of(ctx, pid)}
    assert len(sha_before) == 1
    done_art = artifacts_of(ctx, pid)[0]
    assert ctx.store.absolute_path(done_art).exists()
    jobs_before = len(ctx.queue.list())

    recovered = ctx.queue.recover_orphans(ctx.lease)

    assert recovered == [slow["job_id"]]
    j = ctx.queue.get(slow["job_id"])
    assert j.status == "queued" and j.pid is None and j.started_at is None
    assert ctx.lease.holder() is None
    with sqlite3.connect(settings.db_path) as c:
        assert (
            c.execute("select count(*) from settings where key='gpu_lease'").fetchone()[
                0
            ]
            == 0
        )
    assert len(ctx.queue.list()) == jobs_before
    assert {a.id: a.sha256 for a in artifacts_of(ctx, pid)} == sha_before
    assert ctx.queue.get(done["job_id"]).status == "succeeded"
    ctx.close()


def test_recover_orphans_resets_running_row_with_dead_pid(tmp_path):
    from reelforge.db.models import Job
    from sqlalchemy import update

    ctx = make_ctx(make_settings(tmp_path))
    job = ctx.queue.enqueue(type="artifact.generate", heavy=True)
    with ctx.session_factory() as s, s.begin():
        s.execute(
            update(Job).where(Job.id == job.id).values(status="running", pid=999_999)
        )
    recovered = ctx.queue.recover_orphans(ctx.lease)
    assert recovered == [job.id]
    j = ctx.queue.get(job.id)
    assert j.status == "queued" and j.pid is None
    assert ctx.queue.recover_orphans(ctx.lease) == []
    ctx.close()
