import asyncio
import sys

from reelforge.adapters.base import CancelToken
from reelforge.adapters.runner import run_command

SCRIPT = (
    "import sys, time\n"
    "for i in range(3):\n"
    "    print(f'line {i}', flush=True)\n"
    "    time.sleep(0.2)\n"
    "sys.stderr.write('warn\\n')\n"
)


def test_stdout_lines_streamed_before_exit_and_collected():
    seen: list[tuple[str, float]] = []
    loop_time: list[float] = []

    async def go():
        loop = asyncio.get_running_loop()
        start = loop.time()
        res = await run_command(
            [sys.executable, "-c", SCRIPT],
            timeout_s=20,
            sample_interval_s=0.05,
            on_stdout_line=lambda ln: seen.append((ln, loop.time() - start)),
        )
        loop_time.append(loop.time() - start)
        return res

    res = asyncio.run(go())
    assert [s[0] for s in seen] == ["line 0", "line 1", "line 2"]
    assert seen[0][1] < loop_time[0] - 0.3  # first line arrived while the process still ran
    assert res.stdout == "line 0\nline 1\nline 2\n"
    assert res.stderr == "warn\n" and res.exit_code == 0


def test_stream_cancel_and_timeout_unchanged():
    code = "import time; print('hi', flush=True); time.sleep(30)"
    seen: list[str] = []
    res = asyncio.run(
        run_command(
            [sys.executable, "-c", code],
            timeout_s=1,
            sample_interval_s=0.05,
            on_stdout_line=seen.append,
        )
    )
    assert res.timed_out and seen == ["hi"]

    async def go():
        cancel = CancelToken()
        task = asyncio.ensure_future(
            run_command(
                [sys.executable, "-c", code],
                timeout_s=30,
                cancel=cancel,
                on_stdout_line=seen.append,
            )
        )
        await asyncio.sleep(1.0)
        cancel.cancel()
        return await asyncio.wait_for(task, 20)

    res = asyncio.run(go())
    assert res.cancelled and res.error == "cancelled"


def test_callback_exception_does_not_break_command():
    def boom(_: str) -> None:
        raise RuntimeError("x")

    res = asyncio.run(
        run_command(
            [sys.executable, "-c", "print('a'); print('b')"], timeout_s=20, on_stdout_line=boom
        )
    )
    assert res.exit_code == 0 and res.stdout == "a\nb\n"
