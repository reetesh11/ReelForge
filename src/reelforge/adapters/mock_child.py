"""Tiny child process used by the mock adapter so cancel/timeout/kill/RSS are real."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--kill", action="store_true")
    ns = parser.parse_args(argv)
    deadline = time.monotonic() + ns.sleep
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 0.1))
    if ns.kill:
        os.kill(os.getpid(), signal.SIGKILL)
    if ns.exit_code < 0:  # like a real child killed by a signal: Popen reports -signal
        os.kill(os.getpid(), -ns.exit_code)
    print("mock child done", flush=True)
    return ns.exit_code


if __name__ == "__main__":
    sys.exit(main())
