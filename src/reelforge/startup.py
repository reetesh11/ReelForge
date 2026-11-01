"""`reelforge up`: doctor, migrate, recover jobs, then serve API + worker."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time

import psutil
import typer
import uvicorn

from reelforge.api.app import create_app
from reelforge.config import Settings
from reelforge.context import AppContext
from reelforge.db.migrate import upgrade
from reelforge.doctor import DoctorReport, mark_serving, run_doctor
from reelforge.logging import configure_logging


def format_report(report: DoctorReport) -> list[str]:
    lines: list[str] = []
    for check in report.checks:
        tag = "PASS" if check.status == "pass" else "FAIL"
        lines.append(f"{tag}  {check.name}  {check.severity}  {check.detail}")
        if check.status == "fail" and check.fix:
            lines.append(f"    fix: {check.fix}")
    lines.append(
        f"{report.passed} passed, {report.warnings} warnings, "
        f"{report.blocking_failures} blocking failures"
    )
    return lines


WATCHDOG_POLL_S = 0.01


def _parent_is_uv() -> bool:
    try:
        return psutil.Process(os.getppid()).name() == "uv"
    except psutil.Error:
        return False


def guard_against_orphaning() -> None:
    """Stop when a non-interactive `uv run` wrapper is gone.

    A hard-killed wrapper cannot forward the signal, which would leave the server bound to its
    port. In that setup (parent is `uv`, no terminal) the server also leaves the wrapper's
    process group, so the wrapper's teardown does not race with ours, and a watchdog thread
    asks for a graceful shutdown once the wrapper disappears. Interactive runs are untouched.
    """
    if sys.stdout.isatty() or not _parent_is_uv():
        return
    parent = os.getppid()
    try:
        os.setpgid(0, 0)
    except OSError:
        pass

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(WATCHDOG_POLL_S)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()


def serve(ctx: AppContext) -> None:
    """Run uvicorn with the API and worker until interrupted."""
    guard_against_orphaning()
    settings = ctx.settings
    configure_logging(log_file=settings.data_root / "logs" / "app.log")
    mark_serving({settings.api_port, settings.ui_port})
    config = uvicorn.Config(
        create_app(ctx), host=settings.host, port=settings.api_port, log_level="info"
    )
    uvicorn.Server(config).run()


def run_up(settings: Settings, *, allow_degraded: bool) -> int:
    typer.echo("==> doctor")
    report = run_doctor(settings)
    for line in format_report(report):
        typer.echo(line)
    failing = [c for c in report.checks if c.status == "fail"]
    if report.blocking_failures and not allow_degraded:
        typer.echo(
            f"Refusing to start: {report.blocking_failures} blocking check(s) failed. "
            "Fix them or pass --allow-degraded."
        )
        return 1
    if failing and allow_degraded:
        typer.echo("Starting in degraded mode")
        for check in failing:
            typer.echo(f"  - {check.name}: {check.detail}")

    typer.echo("==> migrate")
    upgrade(settings.db_path)
    ctx = AppContext.create(settings, migrate=False)
    try:
        typer.echo("==> recover jobs")
        recovered = ctx.queue.recover_orphans(ctx.lease)
        typer.echo(f"recovered {len(recovered)} interrupted job(s)")
        typer.echo("==> start API + worker")
        typer.echo(settings.api_url)
        serve(ctx)
    finally:
        ctx.close()
    return 0
