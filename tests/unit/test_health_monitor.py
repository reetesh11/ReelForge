from reelforge.doctor import CheckResult, DoctorReport
from reelforge.events import EventBus
from reelforge.health import HealthMonitor


def _report(failing: set[str]) -> DoctorReport:
    return DoctorReport(
        checks=[
            CheckResult(
                name=n,
                status="fail" if n in failing else "pass",
                severity="blocking",
                detail="d",
                fix="f" if n in failing else None,
            )
            for n in ("a", "b")
        ]
    )


def test_only_changed_checks_are_reported_and_published():
    failing: set[str] = set()
    bus = EventBus()
    q = bus.subscribe()
    mon = HealthMonitor(lambda: _report(failing), bus)
    assert mon.poll_once() == []
    failing.add("b")
    assert [c.name for c in mon.poll_once()] == ["b"]
    assert mon.poll_once() == []
    ev = q.get_nowait()
    assert ev.type == "health.changed" and ev.data == {"service": "b", "status": "fail"}
    assert q.empty()
