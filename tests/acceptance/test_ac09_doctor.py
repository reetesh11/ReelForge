"""AC-9: doctor table, /health parity, up refusing on blocking failures."""

from __future__ import annotations

import socket
from collections import namedtuple

from rf_helpers import free_port, make_client, make_ctx, make_settings, write_models

NAMES = [
    "arm64",
    "binaries_native",
    "ffmpeg_filters",
    "ltx",
    "mlx_audio",
    "draw_things",
    "ollama",
    "ports",
    "disk",
    "memory",
    "licenses",
]
BLOCKING = {
    "arm64",
    "binaries_native",
    "ffmpeg_filters",
    "ltx",
    "mlx_audio",
    "draw_things",
    "ports",
}


def _stub_checks(monkeypatch, fail: dict[str, str] | None = None):
    from reelforge.doctor import CHECKS, CheckResult

    fail = fail or {}
    for name in list(CHECKS):

        def fn(settings, _n=name):
            if _n in fail:
                return CheckResult(
                    name=_n,
                    status="fail",
                    severity=fail[_n],
                    detail=f"{_n} broke",
                    fix=f"fix {_n}",
                )
            return CheckResult(
                name=_n, status="pass", severity="blocking", detail="fine", fix=None
            )

        monkeypatch.setitem(CHECKS, name, fn)


def _invoke(args):
    from reelforge.cli import app
    from typer.testing import CliRunner

    return CliRunner().invoke(app, args)


def test_checks_registry_order():
    from reelforge.doctor import CHECKS

    assert list(CHECKS) == NAMES


def test_report_properties():
    from rf_helpers import passing_report

    r = passing_report({"ltx": "blocking", "ollama": "warning", "memory": "warning"})
    assert (r.passed, r.warnings, r.blocking_failures, r.ok, r.overall) == (
        8,
        2,
        1,
        False,
        "fail",
    )
    r2 = passing_report({"ollama": "warning"})
    assert r2.ok and r2.overall == "degraded"
    assert passing_report().overall == "ok"


def test_run_doctor_turns_exceptions_into_failures(monkeypatch, tmp_path):
    from reelforge.doctor import CHECKS, run_doctor

    _stub_checks(monkeypatch)

    def boom(settings):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(CHECKS, "ltx", boom)
    report = run_doctor(make_settings(tmp_path))
    assert [c.name for c in report.checks] == NAMES
    ltx = report.checks[3]
    assert ltx.status == "fail" and "kaboom" in ltx.detail and ltx.fix


def test_cli_doctor_all_pass(monkeypatch, tmp_path):
    _stub_checks(monkeypatch)
    res = _invoke(["doctor", "--data-root", str(tmp_path / "d")])
    assert res.exit_code == 0, res.output
    lines = [ln for ln in res.output.splitlines() if ln.strip()]
    rows = [ln for ln in lines if ln.startswith(("PASS", "FAIL"))]
    assert len(rows) == 11
    assert [r.split()[1] for r in rows] == NAMES
    assert lines[-1] == "11 passed, 0 warnings, 0 blocking failures"


def test_cli_doctor_blocking_failure_exits_one_with_fix_line(monkeypatch, tmp_path):
    _stub_checks(monkeypatch, {"ltx": "blocking", "ollama": "warning"})
    res = _invoke(["doctor", "--data-root", str(tmp_path / "d")])
    assert res.exit_code == 1
    assert "FAIL  ltx  blocking  ltx broke" in res.output
    assert "    fix: fix ltx" in res.output
    assert "FAIL  ollama  warning" in res.output
    assert (
        res.output.strip().splitlines()[-1]
        == "9 passed, 1 warnings, 1 blocking failures"
    )


def test_cli_doctor_warning_only_exits_zero(monkeypatch, tmp_path):
    _stub_checks(monkeypatch, {"memory": "warning"})
    assert _invoke(["doctor", "--data-root", str(tmp_path / "d")]).exit_code == 0


def test_cli_help_lists_commands_and_config_errors_exit_two(tmp_path):
    res = _invoke(["--help"])
    assert res.exit_code == 0 and "doctor" in res.output and "up" in res.output
    bad = _invoke(["doctor", "--host", "0.0.0.0", "--data-root", str(tmp_path)])
    assert bad.exit_code == 2
    assert "config error" in bad.output and "host" in bad.output
    cfg = tmp_path / "config.toml"
    cfg.write_text("[server\nbroken")
    bad2 = _invoke(["doctor", "--config", str(cfg), "--data-root", str(tmp_path)])
    assert bad2.exit_code == 2 and "config.toml" in bad2.output


def test_up_refuses_on_blocking_failure(monkeypatch, tmp_path):
    _stub_checks(monkeypatch, {"draw_things": "blocking"})
    served: list[object] = []
    monkeypatch.setattr("reelforge.startup.serve", lambda ctx: served.append(ctx))
    root = tmp_path / "d"
    res = _invoke(["up", "--data-root", str(root), "--api-port", "7455"])
    assert res.exit_code == 1
    assert "==> doctor" in res.output
    assert (
        "Refusing to start: 1 blocking check(s) failed. Fix them or pass --allow-degraded."
        in res.output
    )
    assert "==> migrate" not in res.output
    assert not served and not (root / "reelforge.db").exists()


def test_up_allow_degraded_runs_steps_in_order_and_serves(monkeypatch, tmp_path):
    _stub_checks(monkeypatch, {"draw_things": "blocking"})
    served: list[object] = []
    monkeypatch.setattr("reelforge.startup.serve", lambda ctx: served.append(ctx))
    root = tmp_path / "d"
    res = _invoke(
        ["up", "--allow-degraded", "--data-root", str(root), "--api-port", "7455"]
    )
    assert res.exit_code == 0, res.output
    out = res.output
    positions = [
        out.index(s)
        for s in (
            "==> doctor",
            "==> migrate",
            "==> recover jobs",
            "==> start API + worker",
        )
    ]
    assert positions == sorted(positions)
    assert "Starting in degraded mode" in out and "draw_things" in out
    assert len(served) == 1 and (root / "reelforge.db").exists()


def test_up_with_all_checks_passing_starts_without_flag(monkeypatch, tmp_path):
    _stub_checks(monkeypatch)
    served: list[object] = []
    monkeypatch.setattr("reelforge.startup.serve", lambda ctx: served.append(ctx))
    res = _invoke(["up", "--data-root", str(tmp_path / "d"), "--api-port", "7455"])
    assert res.exit_code == 0 and len(served) == 1


def test_health_endpoint_matches_doctor(monkeypatch, tmp_path):
    from reelforge.doctor import run_doctor

    _stub_checks(monkeypatch, {"ltx": "blocking", "ollama": "warning"})
    settings = make_settings(tmp_path)
    ctx = make_ctx(settings, doctor=None)
    ctx.doctor = None  # use the real run_doctor path (stubbed checks)
    with make_client(ctx, start_worker=False) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    report = run_doctor(settings)
    assert body["status"] == "fail" == report.overall
    assert [c["name"] for c in body["checks"]] == NAMES
    assert [(c["name"], c["status"]) for c in body["checks"]] == [
        (c.name, c.status) for c in report.checks
    ]
    assert set(body["checks"][3]) >= {"name", "status", "severity", "detail", "fix"}
    ctx.close()


def test_health_degraded_and_ok(tmp_path):
    from rf_helpers import passing_report

    for fail, expected in (({}, "ok"), ({"ollama": "warning"}, "degraded")):
        ctx = make_ctx(
            make_settings(tmp_path / expected), doctor=lambda f=fail: passing_report(f)
        )
        with make_client(ctx, start_worker=False) as client:
            assert client.get("/health").json()["status"] == expected
        ctx.close()


def test_disk_thresholds(monkeypatch, tmp_path):
    import shutil

    import psutil
    from reelforge.doctor import CHECKS

    Usage = namedtuple("Usage", "total used free percent")
    settings = make_settings(tmp_path)
    for free_gb, status, sev in (
        (50, "pass", None),
        (20, "fail", "warning"),
        (3, "fail", "blocking"),
    ):
        free = int(free_gb * 1024**3)
        monkeypatch.setattr(
            shutil, "disk_usage", lambda p, f=free: Usage(10**13, 10**13 - f, f)
        )
        monkeypatch.setattr(
            psutil, "disk_usage", lambda p, f=free: Usage(10**13, 10**13 - f, f, 50.0)
        )
        res = CHECKS["disk"](settings)
        assert res.status == status
        if sev:
            assert res.severity == sev and res.fix


def test_memory_check_warns_below_24gb_and_shows_available(monkeypatch, tmp_path):
    import psutil
    from reelforge.doctor import CHECKS

    VM = namedtuple("VM", "total available used free percent")
    gb = 1024**3
    monkeypatch.setattr(
        psutil, "virtual_memory", lambda: VM(16 * gb, 5 * gb, 11 * gb, 5 * gb, 68.0)
    )
    res = CHECKS["memory"](make_settings(tmp_path))
    assert res.status == "fail" and res.severity == "warning" and res.fix
    assert "5" in res.detail
    monkeypatch.setattr(
        psutil, "virtual_memory", lambda: VM(64 * gb, 40 * gb, 24 * gb, 30 * gb, 37.0)
    )
    assert CHECKS["memory"](make_settings(tmp_path)).status == "pass"


def test_ports_check_names_port_and_licenses_check_lists_keys(tmp_path):
    from reelforge.doctor import CHECKS

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        res = CHECKS["ports"](make_settings(tmp_path, api_port=port))
    finally:
        s.close()
    assert res.status == "fail" and res.severity == "blocking"
    assert res.detail == f"Port {port} is used by another process."
    assert res.fix
    free = free_port()
    assert (
        CHECKS["ports"](
            make_settings(tmp_path, api_port=free, ui_port=free_port())
        ).status
        == "pass"
    )

    models = tmp_path / "models.toml"
    models.write_text(
        '[models.image]\nid = "a/b"\nrevision = "1"\n\n[models.tts]\nid = "c/d"\nrevision = "2"\n'
    )
    lic = CHECKS["licenses"](make_settings(tmp_path, models_path=models))
    assert lic.status == "fail" and lic.severity == "warning"
    assert "image" in lic.detail and "tts" in lic.detail
    ok = write_models(tmp_path / "ok.toml")
    assert CHECKS["licenses"](make_settings(tmp_path, models_path=ok)).status == "pass"
