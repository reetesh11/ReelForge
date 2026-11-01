"""Health monitor: runs doctor and emits `health.changed` when a check flips."""

from __future__ import annotations

from collections.abc import Callable

from reelforge.doctor import CheckResult, DoctorReport
from reelforge.events import EventBus


class HealthMonitor:
    def __init__(self, run: Callable[[], DoctorReport], bus: EventBus) -> None:
        self._run = run
        self._bus = bus
        self._previous: dict[str, str] | None = None

    def poll_once(self) -> list[CheckResult]:
        report = self._run()
        current = {c.name: c.status for c in report.checks}
        previous, self._previous = self._previous, current
        if previous is None:
            return []
        changed = [c for c in report.checks if previous.get(c.name) != c.status]
        for check in changed:
            self._bus.publish("health.changed", {"service": check.name, "status": check.status})
        return changed
