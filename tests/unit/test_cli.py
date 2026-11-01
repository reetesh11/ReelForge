from typer.testing import CliRunner

from reelforge.cli import app
from reelforge.doctor import CHECKS, CheckResult


def _stub(monkeypatch, fail=None):
    fail = fail or {}
    for name in list(CHECKS):

        def fn(_s, _n=name):
            if _n in fail:
                return CheckResult(
                    name=_n, status="fail", severity=fail[_n], detail="broke", fix="do x"
                )
            return CheckResult(name=_n, status="pass", severity="blocking", detail="ok")

        monkeypatch.setitem(CHECKS, name, fn)


def test_help_and_version():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0 and "doctor" in r.output and "up" in r.output
    assert CliRunner().invoke(app, ["--version"]).output.strip() == "0.1.0"


def test_doctor_exit_codes(monkeypatch, tmp_path):
    root = str(tmp_path / "d")
    _stub(monkeypatch)
    assert CliRunner().invoke(app, ["doctor", "--data-root", root]).exit_code == 0
    _stub(monkeypatch, {"ltx": "blocking"})
    r = CliRunner().invoke(app, ["doctor", "--data-root", root])
    assert r.exit_code == 1 and "    fix: do x" in r.output


def test_bad_host_exits_two(tmp_path):
    r = CliRunner().invoke(app, ["doctor", "--host", "0.0.0.0", "--data-root", str(tmp_path)])
    assert r.exit_code == 2 and "config error" in r.output


def test_up_refuses_then_allows(monkeypatch, tmp_path):
    _stub(monkeypatch, {"ltx": "blocking"})
    served: list[object] = []
    monkeypatch.setattr("reelforge.startup.serve", served.append)
    root = str(tmp_path / "d")
    r = CliRunner().invoke(app, ["up", "--data-root", root])
    assert r.exit_code == 1 and "Refusing to start" in r.output and not served
    r = CliRunner().invoke(app, ["up", "--allow-degraded", "--data-root", root])
    assert r.exit_code == 0 and "Starting in degraded mode" in r.output and len(served) == 1
