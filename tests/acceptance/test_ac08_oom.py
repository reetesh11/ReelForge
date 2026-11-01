"""AC-8: exit -9 and 137 are classified as 'killed, likely out of memory'."""

from __future__ import annotations

import sys

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

OOM = "killed, likely out of memory"


def test_classify_exit_codes():
    from reelforge.jobs.classify import OOM_REASON, classify_exit

    assert OOM_REASON == OOM
    assert classify_exit(-9) == OOM
    assert classify_exit(137) == OOM
    for other in (0, 1, 2, 3, -15, 139, None):
        assert classify_exit(other) is None


def test_runner_classifies_sigkilled_child():
    from reelforge.adapters.runner import run_command

    argv = [
        sys.executable,
        "-c",
        "import os, signal; os.kill(os.getpid(), signal.SIGKILL)",
    ]
    res = run_async(run_command(argv, timeout_s=20, sample_interval_s=0.1))
    assert res.exit_code == -9 and res.error == OOM


def test_runner_classifies_exit_137():
    from reelforge.adapters.runner import run_command

    res = run_async(
        run_command(
            [sys.executable, "-c", "import sys; sys.exit(137)"],
            timeout_s=20,
            sample_interval_s=0.1,
        )
    )
    assert res.exit_code == 137 and res.error == OOM


def test_runner_does_not_flag_ordinary_failures():
    from reelforge.adapters.runner import run_command

    res = run_async(
        run_command(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            timeout_s=20,
            sample_interval_s=0.1,
        )
    )
    assert res.exit_code == 3 and res.error != OOM


def test_job_killed_by_oom_fails_with_reason_after_retry(tmp_path):
    settings = make_settings(tmp_path)
    adapter = CountingAdapter(settings)
    ctx = make_ctx(settings, adapter=adapter)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, params={"mock": {"kill": True}})["job_id"]
        job = wait_job(ctx, job_id, {"succeeded", "failed"})
    assert job.status == "failed"
    assert job.error == OOM
    assert adapter.runs == 2  # OOM is transient: one retry
    ctx.close()
