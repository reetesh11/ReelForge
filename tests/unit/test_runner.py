import asyncio
import pathlib
import sys

import psutil
import structlog
from structlog.testing import capture_logs

from reelforge.adapters.base import CancelToken
from reelforge.adapters.runner import run_command
from reelforge.jobs.classify import OOM_REASON, classify_exit


def test_classify_exit():
    assert classify_exit(-9) == classify_exit(137) == OOM_REASON
    assert [classify_exit(c) for c in (1, 0, None)] == [None, None, None]


def test_argv_logged_verbatim_and_no_shell():
    argv = [sys.executable, "-c", "import sys; print(sys.argv[1])", "$HOME; echo x"]
    structlog.reset_defaults()
    with capture_logs() as logs:
        res = asyncio.run(run_command(argv, timeout_s=20, job_id="j", sample_interval_s=0.05))
    assert res.stdout.strip() == "$HOME; echo x"
    cmd = [e for e in logs if e["event"] == "adapter.command"]
    assert cmd[0]["argv"] == argv and cmd[0]["job_id"] == "j"


def test_timeout_kills_sleeping_child():
    pids: list[int] = []
    res = asyncio.run(
        run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout_s=1,
            on_start=pids.append,
            sample_interval_s=0.05,
        )
    )
    assert res.timed_out and res.error == "timed out after 1s"
    assert not psutil.pid_exists(pids[0])


def test_cancel_kills_child_and_rss_is_sampled():
    async def go():
        token = CancelToken()
        task = asyncio.create_task(
            run_command(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout_s=60,
                cancel=token,
                sample_interval_s=0.05,
            )
        )
        await asyncio.sleep(0.5)
        token.cancel()
        return await task

    res = asyncio.run(go())
    assert res.cancelled and res.peak_rss_mb > 0


def test_log_file_written(tmp_path: pathlib.Path):
    log = tmp_path / "l" / "x.log"
    asyncio.run(
        run_command([sys.executable, "-c", "print('hi-there')"], timeout_s=20, log_path=log)
    )
    assert "hi-there" in log.read_text()


def test_no_shell_true_in_src():
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    pat = re.compile(r"shell\s*=\s*True")
    for base in ("src", "tests/unit", "scripts"):
        for f in (root / base).rglob("*.py") if (root / base).exists() else []:
            if f.name == "test_runner.py":
                continue
            assert not pat.search(f.read_text()), f
