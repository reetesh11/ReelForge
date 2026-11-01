"""AC-11: run the web acceptance suites (vitest + Playwright) as pytest tests.

The suites live in web/tests/acceptance/*.test.tsx and web/e2e/*.spec.ts.
"""

from __future__ import annotations

import subprocess

from rf_helpers import REPO_ROOT


def _run(args: list[str], timeout: int) -> None:
    assert (REPO_ROOT / "web" / "package.json").is_file(), "web/package.json missing"
    res = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert res.returncode == 0, (res.stdout + res.stderr)[-4000:]


def test_vitest_acceptance_suite_passes():
    _run(["pnpm", "--dir", "web", "test", "--run"], timeout=600)


def test_playwright_flows_pass():
    _run(["pnpm", "--dir", "web", "exec", "playwright", "test"], timeout=900)
