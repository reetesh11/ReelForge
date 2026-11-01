from reelforge.config import Settings
from reelforge.doctor import CHECKS, CheckResult, DoctorReport, run_doctor

NAMES = (
    "arm64 binaries_native ffmpeg_filters ltx mlx_audio draw_things "
    "ollama ports disk memory licenses"
)


def _ok(name: str) -> CheckResult:
    return CheckResult(name=name, status="pass", severity="blocking", detail="ok")


def test_registry_order_and_report(tmp_path):
    assert list(CHECKS) == NAMES.split()
    rep = DoctorReport(
        checks=[
            _ok("a"),
            CheckResult(name="b", status="fail", severity="warning", detail="d", fix="f"),
        ]
    )
    assert (rep.passed, rep.warnings, rep.blocking_failures, rep.overall) == (1, 1, 0, "degraded")


def test_exception_becomes_failure(monkeypatch, tmp_path):
    def boom(_s):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(CHECKS, "ltx", boom)
    rep = run_doctor(Settings(data_root=tmp_path))
    ltx = next(c for c in rep.checks if c.name == "ltx")
    assert ltx.status == "fail" and "kaboom" in ltx.detail and ltx.fix


def test_unconfigured_tools_fail_with_fix(tmp_path):
    s = Settings(data_root=tmp_path, drawthings_url="http://127.0.0.1:1")
    for name in ("ltx", "mlx_audio", "draw_things"):
        res = CHECKS[name](s)
        assert res.status == "fail" and res.severity == "blocking" and res.fix


def test_non_loopback_service_url_is_refused(tmp_path):
    s = Settings(data_root=tmp_path, ollama_url="http://example.com:11434")
    res = CHECKS["ollama"](s)
    assert res.status == "fail" and "loopback" in res.detail
