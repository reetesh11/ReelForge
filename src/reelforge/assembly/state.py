"""Small shared error types of the assembly stage."""

from __future__ import annotations

from reelforge.adapters.base import AdapterError


class AssemblyError(Exception):
    """A request-level failure with an HTTP status and a message for the user."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class StepError(AdapterError):
    """A render step failed; `str(exc)` is the reason shown to the user."""

    def __init__(self, step: str, reason: str) -> None:
        super().__init__(reason)
        self.step = step
        self.reason = reason
