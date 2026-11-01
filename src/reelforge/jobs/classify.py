"""Exit-code classification."""

from __future__ import annotations

OOM_REASON = "killed, likely out of memory"


def classify_exit(code: int | None) -> str | None:
    """Return the OOM reason for SIGKILL-style exits (-9, 137), otherwise None."""
    if code in (-9, 137):
        return OOM_REASON
    return None
