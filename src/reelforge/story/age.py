"""Character age in years and the OmniVoice age band it maps to."""

from __future__ import annotations

AGE_ERROR = "Age must be a whole number from 1 to 120."
AGE_MIN = 1
AGE_MAX = 120


def check_age(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not AGE_MIN <= value <= AGE_MAX:
        raise ValueError(AGE_ERROR)
    return value


def age_band(age: int) -> str:
    if age <= 12:
        return "child"
    if age <= 19:
        return "teenager"
    if age <= 39:
        return "young adult"
    if age <= 59:
        return "middle-aged"
    return "elderly"
