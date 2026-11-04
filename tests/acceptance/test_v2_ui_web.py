"""v2 UI redesign: run the web acceptance tests per criterion as pytest tests.

The vitest tests live in web/tests/acceptance/v2_*.test.ts(x); each criterion's describe block starts
with its id ("AC-8 ..."), so `-t "AC-8 "` selects exactly that criterion. AC-2a is a Playwright spec.
"""

from __future__ import annotations

import subprocess

from rf_helpers import REPO_ROOT


def _run(args: list[str], timeout: int) -> None:
    assert (REPO_ROOT / "web" / "package.json").is_file(), "web/package.json missing"
    res = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, check=False)
    assert res.returncode == 0, (res.stdout + res.stderr)[-4000:]


def _vitest(criterion: str) -> None:
    _run(
        ["pnpm", "--dir", "web", "exec", "vitest", "run", "tests/acceptance/v2_", "-t", f"{criterion} "],
        timeout=600,
    )


def test_ac01_sidebar():
    _vitest("AC-1")


def test_ac02_stage_rail_links():
    _vitest("AC-2")


def test_ac02a_stage_rail_geometry():
    _run(["pnpm", "--dir", "web", "exec", "playwright", "test", "e2e/stage-rail.spec.ts"], timeout=900)


def test_ac03_landing_stage():
    _vitest("AC-3")


def test_ac04_stage_param():
    _vitest("AC-4")


def test_ac05_client_navigation():
    _vitest("AC-5")


def test_ac06_next_up():
    _vitest("AC-6")


def test_ac07_header_progress():
    _vitest("AC-7")


def test_ac08_ctas():
    _vitest("AC-8")


def test_ac09_one_cta():
    _vitest("AC-9")


def test_ac10_story_form():
    _vitest("AC-10")


def test_ac11_needs_update():
    _vitest("AC-11")


def test_ac12_unsaved():
    _vitest("AC-12")


def test_ac13a_cast_icons():
    _vitest("AC-13a")


def test_ac13_cast_selection():
    _vitest("AC-13")


def test_ac14_status_strips():
    _vitest("AC-14")


def test_ac15_project_cards():
    _vitest("AC-15")


def test_ac16_no_raw_colours():
    _vitest("AC-16")


def test_ac17_tokens():
    _vitest("AC-17")


def test_ac18_reduced_motion():
    _vitest("AC-18")


def test_ac23_banner_and_messages():
    _vitest("AC-23")
