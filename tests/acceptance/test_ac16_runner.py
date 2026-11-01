"""AC-16: commands are logged verbatim as argument lists; timeouts abort the command."""

from __future__ import annotations

import io
import json
import sys
import time

from rf_helpers import (
    create_project,
    make_client,
    make_ctx,
    make_settings,
    run_async,
    submit,
    wait_job,
)


def _events(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_logging_emits_json_lines_with_required_keys():
    import structlog
    from reelforge.logging import configure_logging

    buf = io.StringIO()
    configure_logging(stream=buf)
    structlog.get_logger().info("hello.world", n=1)
    ev = next(e for e in _events(buf) if e["event"] == "hello.world")
    assert {"ts", "level", "event"} <= set(ev)
    assert ev["level"].lower() == "info" and ev["n"] == 1


def test_command_is_logged_verbatim_as_argv():
    from reelforge.adapters.runner import run_command
    from reelforge.logging import configure_logging

    buf = io.StringIO()
    configure_logging(stream=buf)
    argv = [
        sys.executable,
        "-c",
        "import sys; print('a b  \"c\"', sys.argv[1:])",
        "x y",
        "$HOME",
        ";echo hi",
    ]
    res = run_async(
        run_command(argv, timeout_s=20, job_id="job-1", sample_interval_s=0.1)
    )
    assert res.exit_code == 0 and res.argv == argv
    assert "$HOME" in res.stdout  # no shell expansion happened
    ev = [e for e in _events(buf) if e["event"] == "adapter.command"]
    assert len(ev) == 1
    assert ev[0]["argv"] == argv
    assert ev[0]["timeout_s"] == 20 and ev[0]["job_id"] == "job-1"


def test_timeout_kills_the_command():
    import psutil
    from reelforge.adapters.runner import run_command

    pids: list[int] = []
    argv = [sys.executable, "-c", "import time; time.sleep(60)"]
    t0 = time.monotonic()
    res = run_async(
        run_command(argv, timeout_s=1, on_start=pids.append, sample_interval_s=0.1)
    )
    assert time.monotonic() - t0 < 15
    assert res.timed_out and res.error == "timed out after 1s"
    time.sleep(0.3)
    assert pids and not psutil.pid_exists(pids[0])


def test_run_command_log_file_gets_command_and_peak_rss(tmp_path):
    from reelforge.adapters.runner import run_command

    log = tmp_path / "job.log"
    argv = [sys.executable, "-c", "print('out-marker')"]
    res = run_async(
        run_command(argv, timeout_s=20, log_path=log, sample_interval_s=0.05)
    )
    text = log.read_text()
    assert "out-marker" in text
    assert json.dumps(argv) in text or all(a in text for a in argv)
    assert res.peak_rss_mb >= 0.0


def test_job_timeout_fails_with_reason_and_records_command(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        slow = submit(client, pid, params={"mock": {"sleep_s": 60, "timeout_s": 1}})[
            "job_id"
        ]
        job = wait_job(ctx, slow, {"succeeded", "failed"}, timeout=40)
        assert job.status == "failed" and job.error == "timed out after 1s"
        ok = submit(client, pid, owner_id="fast", seed=5)["job_id"]
        done = wait_job(ctx, ok, {"succeeded", "failed"})
    assert done.status == "succeeded"
    cmd = done.command if isinstance(done.command, list) else json.loads(done.command)
    assert cmd[0] == sys.executable and "reelforge.adapters.mock_child" in cmd
    assert done.log_path and not done.log_path.startswith("/")
    assert (ctx.settings.data_root / done.log_path).exists()
    ctx.close()
